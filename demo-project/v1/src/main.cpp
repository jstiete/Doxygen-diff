#include "Calculator.h"
#include "StringUtils.h"
#include <iostream>

/**
 * @brief Entry point of the demo application.
 *
 * Demonstrates usage of Calculator and StringUtils.
 * @return exit code
 */
int main() {
    Calculator calc;
    int sum = calc.add(2, 3);
    int diff = calc.subtract(5, 2);
    int prod = calc.multiply(4, 6);

    std::string text = StringUtils::trim("  hello  ");
    std::string upper = StringUtils::toUpper(text);

    std::cout << sum << " " << diff << " " << prod << " " << upper << std::endl;
    return 0;
}
