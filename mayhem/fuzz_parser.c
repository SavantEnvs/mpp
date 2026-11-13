/*
 * libFuzzer harness for one Rockchip MPP software bitstream parser. The
 * hardware decoder needs /dev/mpp_service, but each codec's ParserApi
 * (prepare + parse) is plain software. MPP_FUZZ_CODING picks the codec.
 */
#include "parser_driver.h"

#ifndef MPP_FUZZ_CODING
#error "define MPP_FUZZ_CODING (e.g. MPP_VIDEO_CodingAVC)"
#endif

int LLVMFuzzerInitialize(int *argc, char ***argv)
{
    (void)argc;
    (void)argv;
    driver_init(MPP_FUZZ_CODING);
    return 0;
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    return driver_parse(MPP_FUZZ_CODING, data, size, NULL) ? -1 : 0;
}
