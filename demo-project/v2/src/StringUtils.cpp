#include "StringUtils.h"
#include <cctype>
#include <algorithm>

namespace StringUtils {

std::string toUpper(const std::string& input) {
    std::string result = input;
    std::transform(result.begin(), result.end(), result.begin(), ::toupper);
    return result;
}

}
