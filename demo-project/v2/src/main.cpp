#include "Calculator.h"
#include "StringUtils.h"
#include "TextUtils.h"
#include <iostream>

/**
 * @brief Logs a labeled result to standard output.
 * @param label a short label for the value
 * @param value the value to log
 */
void logResult(const std::string& label, int value) {
    std::cout << label << "=" << value << " ";
}

/**
 * @brief Entry point of the demo application.
 *
 * Demonstrates usage of Calculator, StringUtils and TextUtils.
 * @return exit code
 */
int main() {
    Calculator calc;
    int sum = calc.add(2, 3);
    int diff = calc.subtract(5, 2);
    int quot = calc.divide(6, 3);

    logResult("sum", sum);
    logResult("diff", diff);
    logResult("quot", quot);

    std::string text = TextUtils::trim("  hello  ");
    std::string upper = StringUtils::toUpper(text);

    std::cout << upper << std::endl;
    return 0;
}
