def scanner(qrcode):
    size = len(qrcode)

    def is_function(row, col):
        top_left = row <= 8 and col <= 8
        top_right = row <= 8 and col >= size - 8
        bottom_left = row >= size - 8 and col <= 8
        return top_left or top_right or bottom_left or row == 6 or col == 6

    bits = []
    upward = True
    for right in range(size - 1, 0, -2):
        if right <= 6:
            right -= 1                      # skip the vertical timing line
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for col in (right, right - 1):
                if not is_function(row, col):
                    bits.append(qrcode[row][col] ^ ((row + col) % 2 == 0))
        upward = not upward

    def byte(start):
        return int("".join(map(str, bits[start:start + 8])), 2)

    length = byte(4)                        # after the 4-bit mode indicator
    return "".join(chr(byte(12 + 8 * i)) for i in range(length))
