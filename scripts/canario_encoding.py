"""Canario de encoding: detecta tildes corrompidas en archivos de texto.

Uso:  python scripts/canario_encoding.py RUTA [RUTA ...]

Falla (código de salida 1) si algún archivo:
  - no es UTF-8 válido,
  - empieza con BOM,
  - contiene U+FFFD (carácter de reemplazo),
  - contiene mojibake típico (UTF-8 leído como Windows-1252).
Los patrones se construyen con chr() para que este archivo pase su propio control.
"""
import sys
from pathlib import Path

A_TILDE = chr(0xC3)  # primer byte de á, é, í, ó, ú, ñ, Ñ visto como Windows-1252

PATRONES = {
    chr(0xFFFD): "U+FFFD (carácter de reemplazo)",
    A_TILDE + chr(0xA1): "mojibake de á",
    A_TILDE + chr(0xA9): "mojibake de é",
    A_TILDE + chr(0xAD): "mojibake de í",
    A_TILDE + chr(0xB3): "mojibake de ó",
    A_TILDE + chr(0xBA): "mojibake de ú",
    A_TILDE + chr(0xB1): "mojibake de ñ",
    A_TILDE + chr(0x2018): "mojibake de Ñ",
    chr(0xC2): "mojibake (A circunfleja suelta)",
}


def revisar(ruta: Path) -> list[str]:
    problemas = []
    datos = ruta.read_bytes()
    if datos.startswith(b"\xef\xbb\xbf"):
        problemas.append("empieza con BOM UTF-8")
    try:
        texto = datos.decode("utf-8")
    except UnicodeDecodeError as exc:
        return problemas + [f"no es UTF-8 válido (byte {exc.start})"]
    for numero, linea in enumerate(texto.splitlines(), start=1):
        for patron, descripcion in PATRONES.items():
            if patron in linea:
                problemas.append(f"línea {numero}: {descripcion}")
    return problemas


def main(argumentos: list[str]) -> int:
    if not argumentos:
        print("Uso: python scripts/canario_encoding.py RUTA [RUTA ...]")
        return 2
    fallas = 0
    for argumento in argumentos:
        ruta = Path(argumento)
        if not ruta.is_file():
            print(f"FALLA  {argumento}: no existe o no es un archivo")
            fallas += 1
            continue
        problemas = revisar(ruta)
        if problemas:
            fallas += 1
            for problema in problemas:
                print(f"FALLA  {argumento}: {problema}")
        else:
            print(f"OK     {argumento}")
    print(f"Canario de encoding: {len(argumentos) - fallas} OK, {fallas} con fallas, {len(argumentos)} revisados")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
