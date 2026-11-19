#pragma once
#include <string>

/**
 * @brief Utility functions for string handling.
 *
 * \mermaid{Typical usage sequence}
 * sequenceDiagram
 *     participant Caller
 *     participant StringUtils
 *     Caller->>StringUtils: toUpper(input)
 *     StringUtils-->>Caller: result
 * \endmermaid
 */
namespace StringUtils {

    /**
     * @brief Converts a string to upper case.
     * @param input the input string
     * @return the upper case version of the input
     */
    std::string toUpper(const std::string& input);

    /**
     * @brief Trims leading and trailing whitespace.
     * @param input the input string
     * @return the trimmed string
     */
    std::string trim(const std::string& input);

}
