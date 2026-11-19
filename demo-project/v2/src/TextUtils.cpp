#include "TextUtils.h"

namespace TextUtils {

std::string trim(const std::string& input) {
    size_t start = input.find_first_not_of(" \t\n\r");
    size_t end = input.find_last_not_of(" \t\n\r");
    if (start == std::string::npos) return "";
    return input.substr(start, end - start + 1);
}

}
