// Лабораторна робота №7 — «Захист даних»
// Codewars: Decode the QR-Code
//
// Самоперевірка розв'язку, надісланого на платформу. Сам розв'язок
// (клас CodeWars) підключено з solution/CodeWars.cs без копіювання, тож
// тут перевіряється буквально той самий код.
//
// Запуск:
//   dotnet run --project csharp/QrScanner -- selftest
//   dotnet run --project csharp/QrScanner -- scan matrix.txt
//   dotnet run --project csharp/QrScanner -- scan-batch matrices.txt
//   dotnet run --project csharp/QrScanner -- bench 200000

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace Lab7.QrScanner;

public static class Program
{
    public static int Main(string[] args)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        if (args.Length == 0) return Usage();
        return args[0] switch
        {
            "selftest" => SelfTest(),
            "scan" when args.Length > 1 => Scan(args[1]),
            "scan-batch" when args.Length > 1 => ScanBatch(args[1]),
            "bench" => Bench(args.Length > 1 ? int.Parse(args[1]) : 200_000),
            _ => Usage(),
        };
    }

    private static int Usage()
    {
        Console.Error.WriteLine("вживання: selftest | scan <файл> | scan-batch <файл> | bench [повтори]");
        return 2;
    }

    /// <summary>Контрольні матриці: тести C#- і Python-версій kata та приклад з умови.</summary>
    private static List<(string Source, string Test, string Expected, int[][] Matrix)> LoadCases()
    {
        string path = FindUp(Path.Combine("tests", "codewars_cases.json"));
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        var cases = new List<(string, string, string, int[][])>();
        foreach (var c in doc.RootElement.GetProperty("cases").EnumerateArray())
        {
            int[][] matrix = c.GetProperty("matrix").EnumerateArray()
                .Select(row => row.GetString()!.Select(ch => ch - '0').ToArray())
                .ToArray();
            cases.Add((c.GetProperty("source").GetString()!, c.GetProperty("test").GetString()!,
                       c.GetProperty("expected").GetString()!, matrix));
        }
        return cases;
    }

    private static string FindUp(string relative)
    {
        foreach (string start in new[] { Directory.GetCurrentDirectory(), AppContext.BaseDirectory })
        {
            for (var dir = new DirectoryInfo(start); dir != null; dir = dir.Parent)
            {
                string candidate = Path.Combine(dir.FullName, relative);
                if (File.Exists(candidate)) return candidate;
            }
        }
        throw new FileNotFoundException($"не знайдено {relative}");
    }

    private static int SelfTest()
    {
        int failures = 0;
        var cases = LoadCases();

        // 1. Контрольні матриці платформи.
        foreach (var (source, test, expected, matrix) in cases)
        {
            string got = CodeWars.Scanner(matrix);
            bool ok = got == expected;
            failures += ok ? 0 : 1;
            Console.WriteLine($"[{(ok ? "OK" : "FAIL")}] {source,-9} {test,-26} -> \"{got}\"");
        }

        // 2. Kata-декодер використовує лише біти довжини й символів: інверсія
        //    модуля поза ними (режим, заповнювачі, байти корекції) не змінює результату.
        var (_, _, warrior, original) = cases.First(c => c.Expected == "Warrior");
        int unaffected = 0, positions = 0;
        for (int row = 0; row < 21; row++)
        {
            for (int col = 0; col < 21; col++)
            {
                int[][] copy = original.Select(r => (int[])r.Clone()).ToArray();
                copy[row][col] ^= 1;
                string got;
                try { got = CodeWars.Scanner(copy); }
                catch (ArgumentOutOfRangeException) { got = "<помилка>"; }
                positions++;
                if (got == warrior) unaffected++;
            }
        }
        Console.WriteLine($"інверсія одного модуля «Warrior»: результат не змінився в {unaffected} з {positions} позицій");
        failures += unaffected == positions - 64 ? 0 : 1;   // 64 = 8 бітів довжини + 7·8 бітів тексту

        Console.WriteLine(failures == 0 ? "пройдено все" : $"FAIL: {failures}");
        return failures == 0 ? 0 : 1;
    }

    private static int[][] ParseMatrix(IEnumerable<string> lines) =>
        lines.Select(l => l.Where(ch => "01#.".Contains(ch)).Select(ch => ch is '1' or '#' ? 1 : 0).ToArray())
             .Where(r => r.Length > 0)
             .ToArray();

    private static int Scan(string path)
    {
        Console.WriteLine(CodeWars.Scanner(ParseMatrix(File.ReadAllLines(path))));
        return 0;
    }

    /// <summary>Кілька матриць через порожній рядок; результати — JSON-масив рядків.</summary>
    private static int ScanBatch(string path)
    {
        var results = new List<string>();
        var block = new List<string>();
        foreach (string line in File.ReadAllLines(path).Append(""))
        {
            if (line.Trim().Length == 0)
            {
                if (block.Count > 0) results.Add(CodeWars.Scanner(ParseMatrix(block)));
                block.Clear();
            }
            else
            {
                block.Add(line);
            }
        }
        Console.WriteLine(JsonSerializer.Serialize(results));
        return 0;
    }

    /// <summary>Середній час одного виклику Scanner на дев'яти контрольних матрицях.</summary>
    private static int Bench(int iterations)
    {
        var matrices = LoadCases().Select(c => c.Matrix).ToArray();
        for (int i = 0; i < 20_000; i++) CodeWars.Scanner(matrices[i % matrices.Length]);   // прогрівання JIT
        var samples = new List<double>();
        int sink = 0;
        for (int repeat = 0; repeat < 5; repeat++)
        {
            var sw = Stopwatch.StartNew();
            for (int i = 0; i < iterations; i++) sink += CodeWars.Scanner(matrices[i % matrices.Length]).Length;
            sw.Stop();
            samples.Add(sw.Elapsed.TotalMilliseconds * 1_000_000.0 / iterations);
        }
        samples.Sort();
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            iterations,
            repeats = samples.Count,
            ns_per_scan_median = samples[samples.Count / 2],
            ns_per_scan_all = samples,
            dotnet = Environment.Version.ToString(),
            checksum = sink,
        }));
        return 0;
    }
}
