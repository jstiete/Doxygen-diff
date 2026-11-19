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
 *     Compute --> Return([Return result])
 * \endmermaid
 */
class Calculator {
public:
    /**
     * @brief Adds two numbers.
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
     * @brief Multiplies two numbers.
     * @param a first operand
     * @param b second operand
     * @return product of a and b
     */
    int multiply(int a, int b);
};
