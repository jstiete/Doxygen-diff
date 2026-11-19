#pragma once

/**
 * @brief A simple calculator class.
 *
 * Provides basic arithmetic operations for integers.
 *
 * \mermaid{Control flow of a typical operation}
 * flowchart TD
 *     Start([Start]) --> Validate{Inputs valid?}
 *     Validate -- no --> Error[Return error]
 *     Validate -- yes --> Compute[Compute result]
 *     Compute --> Overflow{Overflow?}
 *     Overflow -- yes --> Error
 *     Overflow -- no --> Return([Return result])
 * \endmermaid
 */
class Calculator {
public:
    /**
     * @brief Adds two numbers.
     *
     * This method performs an integer addition of the two given operands
     * and returns the result. Overflow is not checked.
     * @param a first operand
     * @param b second operand
     * @return sum of a and b
     */
    int add(int a, int b);

    /**
     * @brief Subtracts b from a.
     * @param a first operand
     * @param b second operand
     * @return difference of a and b
     */
    int subtract(int a, int b);

    /**
     * @brief Divides a by b.
     * @param a numerator
     * @param b denominator, must not be zero
     * @return quotient of a and b
     */
    int divide(int a, int b);
};
