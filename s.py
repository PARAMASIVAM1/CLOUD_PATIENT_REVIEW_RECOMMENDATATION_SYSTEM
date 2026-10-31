def generate_matrix(key):
    key = key.upper().replace("J", "I")
    matrix = []
    used = set()

    for char in key:
        if char not in used and char.isalpha():
            used.add(char)
            matrix.append(char)

    for char in "ABCDEFGHIKLMNOPQRSTUVWXYZ":
        if char not in used:
            used.add(char)
            matrix.append(char)

    return [matrix[i:i+5] for i in range(0, 25, 5)]

def find_position(matrix, char):
    for i in range(5):
        for j in range(5):
            if matrix[i][j] == char:
                return i, j

def playfair_decrypt(cipher, key):
    matrix = generate_matrix(key)
    cipher = cipher.upper().replace("J", "I")

    result = ""

    for i in range(0, len(cipher), 2):
        a, b = cipher[i], cipher[i+1]

        row1, col1 = find_position(matrix, a)
        row2, col2 = find_position(matrix, b)

        if row1 == row2:
            result += matrix[row1][(col1 - 1) % 5]
            result += matrix[row2][(col2 - 1) % 5]

        elif col1 == col2:
            result += matrix[(row1 - 1) % 5][col1]
            result += matrix[(row2 - 1) % 5][col2]




        else:
            result += matrix[row1][col2]
            result += matrix[row2][col1]
    return result
key = "SECURITY"
cipher = "UBXDQK"
print("Decrypted:", playfair_decrypt(cipher, key))


