#include "StringUtils.h"
#include <cctype>
#include <algorithm>

namespace StringUtils {

std::string toUpper(const std::string& input) {
    std::string result = input;
    std::transform(result.begin(), result.end(), result.begin(), ::toupper);
    return result;
}

std::string trim(const std::string& input) {
    size_t start = input.find_first_not_of(" \t\n\r");
    size_t end = input.find_last_not_of(" \t\n\r");
    if (start == std::string::npos) return "";
    return input.substr(start, end - start + 1);
}

}
