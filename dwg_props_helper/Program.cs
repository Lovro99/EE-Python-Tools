/*
 * dwg_props_helper — ACadSharp DWG custom-property writer
 *
 * Koristi se iz Pythona (syncDwgFast.py) via subprocess.
 *
 * Poziv:
 *   dwg_props_helper.exe <putanja_do_dwg> <json_properties>
 *
 * JSON format:  {"Naziv1":"Vrijednost1","Naziv2":"Vrijednost2",...}
 *
 * Stdout linije:
 *   OK|<poruka>      — uspješna operacija
 *   WARN|<poruka>    — upozorenje (npr. case mismatch)
 *   INFO|<poruka>    — informacija
 *
 * Exit code:  0 = uspjeh,  1 = greška (stderr sadrži opis)
 *
 * Build (jednom):
 *   dotnet publish -c Release -r win-x64 --self-contained
 */

using ACadSharp.IO;
using System.Text.Json;

// ── Provjera argumenata ───────────────────────────────────────────────────────
if (args.Length < 2)
{
    Console.Error.WriteLine("Korištenje: dwg_props_helper.exe <dwg_putanja> <json_properties>");
    return 1;
}

var dwgPath  = args[0];
var jsonArgs = args[1];

if (!File.Exists(dwgPath))
{
    Console.Error.WriteLine($"Datoteka ne postoji: {dwgPath}");
    return 1;
}

// ── Parsiraj JSON properties ──────────────────────────────────────────────────
Dictionary<string, string> props;
try
{
    props = JsonSerializer.Deserialize<Dictionary<string, string>>(jsonArgs)
            ?? throw new Exception("JSON je null");
}
catch (Exception ex)
{
    Console.Error.WriteLine($"Greška pri parsiranju JSON-a: {ex.Message}");
    return 1;
}

// ── Čitaj DWG ─────────────────────────────────────────────────────────────────
ACadSharp.CadDocument doc;
try
{
    Console.WriteLine($"INFO|Čitam: {Path.GetFileName(dwgPath)}");
    using var reader = new DwgReader(dwgPath);
    doc = reader.Read();
}
catch (Exception ex)
{
    Console.Error.WriteLine($"Greška pri čitanju DWG: {ex.Message}");
    return 1;
}

// ── Upiši properties (case-insensitive lookup) ────────────────────────────────
int okN = 0, warnN = 0, errN = 0;

var customProps = doc.SummaryInfo.Properties;

foreach (var (name, value) in props)
{
    try
    {
        // Pronađi postojeći ključ bez obzira na velika/mala slova
        var existingKey = customProps.Keys
            .FirstOrDefault(k => k.Equals(name, StringComparison.OrdinalIgnoreCase));

        if (existingKey is not null)
        {
            if (!existingKey.Equals(name, StringComparison.Ordinal))
            {
                Console.WriteLine($"WARN|Naziv '{name}' (Excel) ≠ '{existingKey}' (DWG) — ažuriram '{existingKey}'");
                warnN++;
            }
            customProps[existingKey] = value;
        }
        else
        {
            customProps[name] = value;
        }
        okN++;
    }
    catch (Exception ex)
    {
        Console.WriteLine($"WARN|Ne mogu postaviti '{name}': {ex.Message}");
        errN++;
    }
}

// ── Spremi DWG ────────────────────────────────────────────────────────────────
try
{
    using var writer = new DwgWriter(dwgPath, doc);
    writer.Write();
}
catch (Exception ex)
{
    Console.Error.WriteLine($"Greška pri snimanju DWG: {ex.Message}");
    return 1;
}

// ── Rezultat ──────────────────────────────────────────────────────────────────
var levelOut = errN > 0 ? "WARN" : "OK";
Console.WriteLine($"{levelOut}|Upisano {okN} svojstava, {warnN} upozorenja, {errN} grešaka.");
return errN > 0 ? 1 : 0;
