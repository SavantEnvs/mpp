/*
 * Oracle probe: parse a bitstream file with one MPP software parser and print
 * what it recovered, e.g. "codec=h264 tasks=1 frames=1 parse_errors=0 width=64 height=48".
 */
#include <stdio.h>

#include "parser_driver.h"

static const struct {
    const char *name;
    MppCodingType coding;
} codecs[] = {
    { "h264",  MPP_VIDEO_CodingAVC },
    { "h265",  MPP_VIDEO_CodingHEVC },
    { "vp9",   MPP_VIDEO_CodingVP9 },
    { "av1",   MPP_VIDEO_CodingAV1 },
    { "mpeg2", MPP_VIDEO_CodingMPEG2 },
    { "mpeg4", MPP_VIDEO_CodingMPEG4 },
    { "h263",  MPP_VIDEO_CodingH263 },
    { "vp8",   MPP_VIDEO_CodingVP8 },
    { "jpeg",  MPP_VIDEO_CodingMJPEG },
    { "avs",   MPP_VIDEO_CodingAVS },
    { "avs2",  MPP_VIDEO_CodingAVS2 },
};

int main(int argc, char **argv)
{
    ParseResult res;
    uint8_t *buf;
    long len;
    FILE *fp;
    size_t i;

    if (argc != 3) {
        fprintf(stderr, "usage: %s <h264|h265|vp9|av1|mpeg2|mpeg4|h263|vp8|jpeg|avs|avs2> <file>\n", argv[0]);
        return 2;
    }
    for (i = 0; i < sizeof(codecs) / sizeof(codecs[0]); i++) {
        if (!strcmp(argv[1], codecs[i].name))
            break;
    }
    if (i == sizeof(codecs) / sizeof(codecs[0])) {
        fprintf(stderr, "unknown codec %s\n", argv[1]);
        return 2;
    }

    fp = fopen(argv[2], "rb");
    if (!fp) {
        perror(argv[2]);
        return 2;
    }
    fseek(fp, 0, SEEK_END);
    len = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    buf = (uint8_t *)malloc(len > 0 ? len : 1);
    if (!buf || len <= 0 || fread(buf, 1, len, fp) != (size_t)len) {
        fprintf(stderr, "cannot read %s\n", argv[2]);
        return 2;
    }
    fclose(fp);

    driver_init(codecs[i].coding);
    if (driver_parse(codecs[i].coding, buf, len, &res)) {
        fprintf(stderr, "parser rejected input\n");
        return 1;
    }
    printf("codec=%s tasks=%d frames=%d parse_errors=%d width=%d height=%d\n",
           codecs[i].name, res.tasks, res.frames, res.parse_errors, res.width, res.height);
    free(buf);
    return 0;
}
