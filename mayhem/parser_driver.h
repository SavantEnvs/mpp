/*
 * Drives one MPP software bitstream parser (ParserApi prepare + parse) the way
 * mpp_dec_no_thread.c does, minus the hardware: split the packet into tasks
 * (prepare), parse each task, then release the slots the hardware would have.
 * Shared by the fuzz harness and the oracle probe.
 */
#ifndef PARSER_DRIVER_H
#define PARSER_DRIVER_H

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "rk_type.h"
#include "mpp_err.h"
#include "mpp_log.h"
#include "mpp_packet.h"
#include "mpp_frame.h"
#include "mpp_buf_slot.h"
#include "mpp_dec_cfg.h"
#include "mpp_parser.h"
#include "parser_api.h"
#include "hal_dec_task.h"
#include "mpp_soc.h"

#define DRIVER_MAX_INPUT    (1u << 20)
#define DRIVER_MAX_TASKS    64

typedef struct ParseResult_t {
    int tasks;
    int frames;
    int parse_errors;
    int width;
    int height;
} ParseResult;

extern MPP_RET mpp_dec_cfg_init(MppDecCfg *cfg);
extern void *kmpp_obj_to_entry(void *obj);

static MppDecCfg g_cfg_obj;
static MppDecCfgSet *g_cfg;

static const MppDecHwCap g_hw_cap = {
    .cap_coding = 0xffffffffu,
    .type = VPU_CLIENT_RKVDEC,
    .cap_4k = 1,
    .cap_8k = 1,
    .cap_10bit = 1,
    .cap_core_num = 1,
};

static void driver_init(MppCodingType coding)
{
    mpp_set_log_level(MPP_LOG_SILENT);
    if (mpp_dec_cfg_init(&g_cfg_obj))
        abort();
    g_cfg = (MppDecCfgSet *)kmpp_obj_to_entry(g_cfg_obj);
    g_cfg->base.type = MPP_CTX_DEC;
    g_cfg->base.coding = coding;
}

static void driver_release_slots(MppBufSlots frame_slots, MppBufSlots packet_slots,
                                 HalDecTask *task)
{
    RK_S32 index = -1;
    RK_U32 i;

    if (task->input >= 0) {
        mpp_buf_slot_clr_flag(packet_slots, task->input, SLOT_HAL_INPUT);
        mpp_buf_slot_clr_flag(packet_slots, task->input, SLOT_CODEC_READY);
    }
    if (task->output >= 0)
        mpp_buf_slot_clr_flag(frame_slots, task->output, SLOT_HAL_OUTPUT);
    for (i = 0; i < MAX_DEC_REF_NUM; i++) {
        if (task->refer[i] >= 0)
            mpp_buf_slot_clr_flag(frame_slots, task->refer[i], SLOT_HAL_INPUT);
    }
    while (MPP_OK == mpp_buf_slot_dequeue(frame_slots, &index, QUEUE_DISPLAY))
        mpp_buf_slot_clr_flag(frame_slots, index, SLOT_QUEUE_USE);
}

static void driver_task_reset(HalDecTask *task)
{
    memset(task, 0, sizeof(*task));
    task->output = -1;
    task->input = -1;
    memset(task->refer, -1, sizeof(task->refer));
}

/* returns 0 when the parser ran, -1 when the input was rejected up front */
static int driver_parse(MppCodingType coding, const uint8_t *data, size_t size,
                        ParseResult *res)
{
    MppBufSlots frame_slots = NULL;
    MppBufSlots packet_slots = NULL;
    Parser parser = NULL;
    MppPacket pkt = NULL;
    MppPacket eos_pkt = NULL;
    MppFrame info = NULL;
    HalDecTask task;
    ParserCfg cfg;
    uint8_t *copy;
    int n;

    if (res)
        memset(res, 0, sizeof(*res));
    if (size == 0 || size > DRIVER_MAX_INPUT)
        return -1;

    copy = (uint8_t *)malloc(size + 64);
    if (!copy)
        return -1;
    memcpy(copy, data, size);
    memset(copy + size, 0, 64);

    if (mpp_buf_slot_init(&frame_slots) || mpp_buf_slot_init(&packet_slots))
        abort();
    mpp_buf_slot_set_dec_cfg(frame_slots, g_cfg_obj);
    mpp_buf_slot_setup(packet_slots, 2);

    memset(&cfg, 0, sizeof(cfg));
    cfg.coding = coding;
    cfg.frame_slots = frame_slots;
    cfg.packet_slots = packet_slots;
    cfg.cfg = g_cfg;
    cfg.hw_info = &g_hw_cap;
    if (mpp_parser_init(&parser, &cfg) != MPP_OK) {
        mpp_buf_slot_deinit(frame_slots);
        mpp_buf_slot_deinit(packet_slots);
        free(copy);
        return -1;
    }

    mpp_packet_init(&pkt, copy, size);
    mpp_packet_set_pts(pkt, 0);
    mpp_packet_set_dts(pkt, 0);
    mpp_packet_init(&eos_pkt, copy, 0);
    mpp_packet_set_eos(eos_pkt);

    for (n = 0; n < DRIVER_MAX_TASKS; n++) {
        MppPacket cur = mpp_packet_get_length(pkt) ? pkt : eos_pkt;
        RK_S32 slot = -1;

        driver_task_reset(&task);
        mpp_parser_prepare(parser, cur, &task);

        if (!task.valid || !task.input_packet) {
            if (cur == eos_pkt || task.flags.eos)
                break;
            if (!mpp_packet_get_length(pkt))
                continue;
            break;
        }

        if (mpp_buf_slot_get_unused(packet_slots, &slot) || slot < 0)
            break;
        task.input = slot;
        mpp_buf_slot_set_flag(packet_slots, slot, SLOT_CODEC_READY);
        mpp_buf_slot_set_flag(packet_slots, slot, SLOT_HAL_INPUT);

        mpp_parser_parse(parser, &task);

        if (res) {
            res->tasks++;
            if (task.flags.parse_err)
                res->parse_errors++;
            else if (task.output >= 0)
                res->frames++;
        }
        if (mpp_buf_slot_is_changed(frame_slots))
            mpp_buf_slot_ready(frame_slots);
        driver_release_slots(frame_slots, packet_slots, &task);
        if (task.flags.eos)
            break;
    }

    mpp_parser_flush(parser);

    if (res && mpp_frame_init(&info) == MPP_OK) {
        if (mpp_slots_get_prop(frame_slots, SLOTS_FRAME_INFO, info) == MPP_OK) {
            res->width = mpp_frame_get_width(info);
            res->height = mpp_frame_get_height(info);
        }
        mpp_frame_deinit(&info);
    }

    mpp_parser_deinit(parser);
    mpp_packet_deinit(&pkt);
    mpp_packet_deinit(&eos_pkt);
    mpp_buf_slot_deinit(frame_slots);
    mpp_buf_slot_deinit(packet_slots);
    free(copy);
    return 0;
}

#endif /* PARSER_DRIVER_H */
