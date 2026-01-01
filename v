# factorial.py

# Function to calculate the factorial of a number
# The function should take an integer as input and return an integer as output.
def factorial(n):
    # AI might suggest the following code:
    if n == 0:
        return 1
    else:
        return n * factorial(n - 1)

# Example usage:
num = 5
print(f"The factorial of {num} is {factorial(num)}")
