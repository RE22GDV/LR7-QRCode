using System;
using System.Collections.Generic;
using System.Text;

public class CodeWars
{
    private const int Size = 21;

    public static string Scanner(int[][] qrcode)
    {
        List<int> bits = ReadDataBits(qrcode);

        // 4 bits of mode (always 0100 = byte mode), then 8 bits of length.
        int length = ReadByte(bits, 4);
        var text = new StringBuilder(length);
        for (int i = 0; i < length; i++)
        {
            text.Append((char)ReadByte(bits, 12 + 8 * i));
        }
        return text.ToString();
    }

    // Zigzag through column pairs from the bottom-right corner, skipping
    // function patterns, and remove mask 0: invert where (row + col) % 2 == 0.
    private static List<int> ReadDataBits(int[][] qrcode)
    {
        var bits = new List<int>(208);
        bool upward = true;
        for (int right = Size - 1; right > 0; right -= 2)
        {
            int pair = right <= 6 ? right - 1 : right;   // column 6 is the timing line
            for (int step = 0; step < Size; step++)
            {
                int row = upward ? Size - 1 - step : step;
                for (int col = pair; col >= pair - 1; col--)
                {
                    if (IsFunctionModule(row, col)) continue;
                    int bit = qrcode[row][col];
                    if ((row + col) % 2 == 0) bit ^= 1;
                    bits.Add(bit);
                }
            }
            upward = !upward;
        }
        return bits;
    }

    // Finder patterns with separators and format areas, plus both timing lines.
    private static bool IsFunctionModule(int row, int col)
    {
        bool topLeft = row <= 8 && col <= 8;
        bool topRight = row <= 8 && col >= Size - 8;
        bool bottomLeft = row >= Size - 8 && col <= 8;
        return topLeft || topRight || bottomLeft || row == 6 || col == 6;
    }

    private static int ReadByte(List<int> bits, int start)
    {
        int value = 0;
        for (int i = 0; i < 8; i++)
        {
            value = (value << 1) | bits[start + i];
        }
        return value;
    }
}
