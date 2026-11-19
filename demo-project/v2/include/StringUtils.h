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
 *     Caller->>StringUtils: trim(result)
 *     StringUtils-->>Caller: trimmed
 * \endmermaid
 */
namespace StringUtils {

    /**
     * @brief Converts a string to upper case.
     * @param input the input string
     * @return the upper case version of the input
     */
    std::string toUpper(const std::string& input);

}
