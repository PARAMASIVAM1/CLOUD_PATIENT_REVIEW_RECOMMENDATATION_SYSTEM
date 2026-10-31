def get_key_order(key):
    sorted_key = sorted(list(key))
    order = []
    for char in key:
        order.append(sorted_key.index(char))
    return order


def encrypt(msg, key):
    msg = msg.replace(" ", "").upper()

    cols = len(key)
    rows = (len(msg) + cols - 1) // cols

    # 
    msg += "X" * (rows * cols - len(msg))

    matrix = [list(msg[i:i+cols]) for i in range(0, len(msg), cols)]

    order = get_key_order(key)

    cipher = ""
    for num in range(cols):
        col_index = order.index(num)
        for row in matrix:
            cipher += row[col_index]

    return cipher


def decrypt(cipher, key):
    cols = len(key)
    rows = len(cipher) // cols

    matrix = [[""] * cols for _ in range(rows)]

    order = get_key_order(key)

    index = 0
    for num in range(cols):
        col_index = order.index(num)
        for i in range(rows):
            matrix[i][col_index] = cipher[index]
            index += 1

    msg = ""
    for row in matrix:
        msg += "".join(row)

    return msg.rstrip("X")


message = input("Enter the message: ")
key = input("Enter the key (any unique characters): ")

if len(set(key)) != len(key):
    print("Invalid key! Characters must be unique.")
else:
    cipher = encrypt(message, key)
    print("Encrypted Message:", cipher)

    plain = decrypt(cipher, key)
    print("Decrypted Message:", plain)