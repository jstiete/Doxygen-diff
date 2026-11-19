#pragma once
#include <string>

/**
 * @brief Utility functions for text processing.
 *
 * This header was split off from StringUtils in version 2.
 */
namespace TextUtils {

    /**
     * @brief Trims leading and trailing whitespace.
     * @param input the input string
     * @return the trimmed string
     */
    std::string trim(const std::string& input);

}
