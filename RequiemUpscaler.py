import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import winreg
except ImportError:
    winreg = None


# ============================================================================
# Identidade, Repositórios e Caminhos
# ============================================================================

APP_NAME = "Requiem Upscaler"
APP_VERSION = "1.0.0"

# Troque para "SeuUsuario/SeuRepositorio" no GitHub para habilitar auto-update do .exe
APP_GITHUB_REPO = "SEU_USUARIO/RequiemUpscaler"
OPTISCALER_API = "https://api.github.com/repos/optiscaler/OptiScaler/releases/latest"

APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RequiemUpscaler"
CACHE_DIR = APP_DATA_DIR / "cache"
ARCHIVE_DIR = CACHE_DIR / "archives"
EXTRACTED_DIR = CACHE_DIR / "extracted"
CONFIG_FILE = APP_DATA_DIR / "config.json"

DEFAULT_ICON_NAME = "requiem_jester.ico"
MANIFEST_NAME = ".requiem_upscaler_manifest.json"
BACKUP_DIR_NAME = ".requiem_upscaler_backup"

PROXY_CANDIDATES = [
    "dxgi.dll",
    "winmm.dll",
    "dbghelp.dll",
    "version.dll",
    "wininet.dll",
    "dinput8.dll",
]

ANTICHEAT_MARKERS = [
    "easyanticheat", "eac_launcher", "battleye", "bedaisy",
    "vgk.sys", "vanguard", "faceit", "ricochet",
    "equ8", "nprotect", "gameguard", "xigncode",
]

# Presets globais selecionáveis na interface
PRESET_PROFILES = {
    "Automático (Detectar GPU)": {
        "upscaler": "auto",
        "framegen": "optifg",
        "ini": {
            "FSR": {"FsrAgilitySDKUpgrade": "true"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true", "AllowAsync": "true"},
        },
    },
    "Qualidade Máxima — FSR 4 + OptiFG": {
        "upscaler": "fsr4",
        "framegen": "optifg",
        "ini": {
            "FSR": {"Fsr4Update": "true", "FsrAgilitySDKUpgrade": "true"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true", "AllowAsync": "true"},
        },
    },
    "FSR 4 INT8 Universal (RDNA2/3 & RTX) + OptiFG": {
        "upscaler": "fsr4",
        "framegen": "optifg",
        "ini": {
            "FSR": {"Fsr4Update": "true", "FsrAgilitySDKUpgrade": "true", "Fsr4Model": "0"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true", "AllowAsync": "true"},
        },
    },
    "Equilibrado — FSR 3.1 + OptiFG": {
        "upscaler": "fsr31",
        "framegen": "optifg",
        "ini": {
            "FSR": {"Fsr4Update": "false"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true", "AllowAsync": "true"},
        },
    },
    "Latência Mínima — FSR 3.1 (Sem Frame Gen)": {
        "upscaler": "fsr31",
        "framegen": "none",
        "ini": {
            "FSR": {"Fsr4Update": "false"},
            "OptiFG": {"Enabled": "false"},
        },
    },
    "NVIDIA RTX — FSR 3.1/4 + Nukem Frame Gen": {
        "upscaler": "fsr31",
        "framegen": "nukems",
        "ini": {
            "OptiFG": {"Enabled": "false"},
        },
    },
    "Bridge DX11 (Sekiro / Dark Souls 3 / Legacy)": {
        "upscaler": "fsr31",
        "framegen": "none",
        "ini": {
            "Upscalers": {"Dx11Upscaler": "fsr31_12"},
            "Spoofing": {"Dxgi": "false"},
            "OptiScaler": {"LoadReshade": "true"},
        },
    },
}

# Perfis individuais pré-configurados por jogo
GAME_PROFILES = {
    "sekiro.exe": {
        "name": "Sekiro: Shadows Die Twice",
        "api": "DX11",
        "preset_hint": "Bridge DX11 (Sekiro / Dark Souls 3 / Legacy)",
        "recommended_proxy": "winmm.dll",
        "notes": (
            "Perfil Sekiro (DX11 sem upscaler nativo): usa winmm.dll (evita conflito com Mod Engine/dinput8.dll) "
            "e ativa interop DX12 + ReShade Bridge.\n"
            "Anexe o pacote Bridge (SekiroTSR + ReShade Addon) para gerar motion vectors."
        ),
        "ini_overrides": {
            "Upscalers": {"Dx11Upscaler": "fsr31_12"},
            "Spoofing": {"Dxgi": "false"},
            "OptiScaler": {"LoadReshade": "true"},
        },
    },
    "darksoulsiii.exe": {
        "name": "Dark Souls III",
        "api": "DX11",
        "preset_hint": "Bridge DX11 (Sekiro / Dark Souls 3 / Legacy)",
        "recommended_proxy": "winmm.dll",
        "notes": (
            "Perfil Dark Souls 3 (DX11 sem upscaler nativo): configurado com winmm.dll e Bridge DX11.\n"
            "IMPORTANTE: Jogue apenas em modo OFFLINE ao usar DLLs injetadas para evitar risco de softban."
        ),
        "ini_overrides": {
            "Upscalers": {"Dx11Upscaler": "fsr31_12"},
            "Spoofing": {"Dxgi": "false"},
            "OptiScaler": {"LoadReshade": "true"},
        },
    },
    "eldenring.exe": {
        "name": "Elden Ring",
        "api": "DX12",
        "preset_hint": "Equilibrado — FSR 3.1 + OptiFG",
        "recommended_proxy": "dxgi.dll",
        "notes": (
            "Perfil Elden Ring (DX12): desative o EasyAntiCheat (modo offline / Seamless Co-op) "
            "para carregar o proxy sem bloqueio."
        ),
        "ini_overrides": {
            "Upscalers": {"Dx12Upscaler": "ffx"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true", "AllowAsync": "true"},
        },
    },
    "cyberpunk2077.exe": {
        "name": "Cyberpunk 2077",
        "api": "DX12",
        "preset_hint": "Qualidade Máxima — FSR 4 + OptiFG",
        "recommended_proxy": "dxgi.dll",
        "notes": "Perfil Cyberpunk 2077: Agility SDK Upgrade + HUDFix para FSR 4 / FSR 3.1 + OptiFG.",
        "ini_overrides": {
            "Upscalers": {"Dx12Upscaler": "ffx"},
            "FSR": {"FsrAgilitySDKUpgrade": "true"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true", "AllowAsync": "true"},
        },
    },
    "witcher3.exe": {
        "name": "The Witcher 3: Wild Hunt",
        "api": "DX12",
        "preset_hint": "Qualidade Máxima — FSR 4 + OptiFG",
        "recommended_proxy": "dxgi.dll",
        "notes": "Perfil Witcher 3 Next-Gen (DX12): HUDFix ativo e FFX FSR 4 / 3.1.",
        "ini_overrides": {
            "Upscalers": {"Dx12Upscaler": "ffx"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true", "AllowAsync": "true"},
        },
    },
    "rdr2.exe": {
        "name": "Red Dead Redemption 2",
        "api": "Vulkan / DX12",
        "preset_hint": "Equilibrado — FSR 3.1 + OptiFG",
        "recommended_proxy": "winmm.dll",
        "notes": "Perfil RDR2: usa winmm.dll para evitar conflitos com scripts e ativa Vulkan/DX12 FFX.",
        "ini_overrides": {
            "Upscalers": {"Dx12Upscaler": "ffx", "VulkanUpscaler": "ffx"},
            "OptiFG": {"HUDFix": "true"},
        },
    },
    "hogwartslegacy.exe": {
        "name": "Hogwarts Legacy",
        "api": "DX12",
        "preset_hint": "Qualidade Máxima — FSR 4 + OptiFG",
        "recommended_proxy": "dxgi.dll",
        "notes": "Perfil Hogwarts Legacy (UE4 DX12): OptiFG + HUDFix + FFX.",
        "ini_overrides": {
            "Upscalers": {"Dx12Upscaler": "ffx"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true", "AllowAsync": "true"},
        },
    },
    "starfield.exe": {
        "name": "Starfield",
        "api": "DX12",
        "preset_hint": "Qualidade Máxima — FSR 4 + OptiFG",
        "recommended_proxy": "dxgi.dll",
        "notes": "Perfil Starfield: FSR 4 / 3.1 com OptiFG e HUDFix habilitado.",
        "ini_overrides": {
            "Upscalers": {"Dx12Upscaler": "ffx"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true"},
        },
    },
    "alanwake2.exe": {
        "name": "Alan Wake 2",
        "api": "DX12",
        "preset_hint": "Qualidade Máxima — FSR 4 + OptiFG",
        "recommended_proxy": "dxgi.dll",
        "notes": "Perfil Alan Wake 2: FSR 4 / 3.1 com OptiFG.",
        "ini_overrides": {
            "Upscalers": {"Dx12Upscaler": "ffx"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true"},
        },
    },
    "b1-win64-shipping.exe": {
        "name": "Black Myth: Wukong",
        "api": "DX12",
        "preset_hint": "Qualidade Máxima — FSR 4 + OptiFG",
        "recommended_proxy": "dxgi.dll",
        "notes": "Perfil Black Myth: Wukong (UE5 DX12): FSR 4 / 3.1 com OptiFG + HUDFix.",
        "ini_overrides": {
            "Upscalers": {"Dx12Upscaler": "ffx"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true", "AllowAsync": "true"},
        },
    },
    "gowr.exe": {
        "name": "God of War Ragnarök",
        "api": "DX12",
        "preset_hint": "Qualidade Máxima — FSR 4 + OptiFG",
        "recommended_proxy": "dxgi.dll",
        "notes": "Perfil God of War Ragnarök: FFX FSR 4 / 3.1 + OptiFG.",
        "ini_overrides": {
            "Upscalers": {"Dx12Upscaler": "ffx"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true"},
        },
    },
    "lop-win64-shipping.exe": {
        "name": "Lies of P",
        "api": "DX12",
        "preset_hint": "Qualidade Máxima — FSR 4 + OptiFG",
        "recommended_proxy": "dxgi.dll",
        "notes": "Perfil Lies of P (UE4 DX12): FFX FSR 4 / 3.1 + OptiFG.",
        "ini_overrides": {
            "Upscalers": {"Dx12Upscaler": "ffx"},
            "OptiFG": {"Enabled": "true", "HUDFix": "true"},
        },
    },
}


# ============================================================================
# Gerador Procedural de Ícone Medieval Jester (.ico 32-bit RGBA)
# ============================================================================

def _draw_jester_bitmap(size: int) -> bytes:
    """Desenha um ícone RGBA de Bobo da Corte Medieval (chapéu 3 pontas, guizos, máscara)."""
    pixels = bytearray(size * size * 4)

    def blend_px(x: int, y: int, r: int, g: int, b: int, a: int = 255):
        if not (0 <= x < size and 0 <= y < size) or a <= 0:
            return
        idx = (y * size + x) * 4
        # BMP bottom-up dentro do formato ICO
        inv_y = size - 1 - y
        idx = (inv_y * size + x) * 4
        if a == 255 or pixels[idx + 3] == 0:
            pixels[idx:idx + 4] = bytes((b, g, r, a))
        else:
            fa = a / 255.0
            fb = pixels[idx + 3] / 255.0
            out_a = fa + fb * (1.0 - fa)
            if out_a > 0:
                pixels[idx] = int((b * fa + pixels[idx] * fb * (1.0 - fa)) / out_a)
                pixels[idx + 1] = int((g * fa + pixels[idx + 1] * fb * (1.0 - fa)) / out_a)
                pixels[idx + 2] = int((r * fa + pixels[idx + 2] * fb * (1.0 - fa)) / out_a)
                pixels[idx + 3] = int(out_a * 255)

    def fill_circle(cx: float, cy: float, radius: float, color: tuple[int, int, int, int]):
        r, g, b, a = color
        x0 = max(0, int(cx - radius - 1))
        x1 = min(size - 1, int(cx + radius + 1))
        y0 = max(0, int(cy - radius - 1))
        y1 = min(size - 1, int(cy + radius + 1))
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                if d <= radius:
                    blend_px(x, y, r, g, b, a)

    def fill_poly(pts: list[tuple[float, float]], color: tuple[int, int, int, int]):
        r, g, b, a = color
        ys = [p[1] for p in pts]
        xs = [p[0] for p in pts]
        y0 = max(0, int(min(ys)))
        y1 = min(size - 1, int(max(ys)))
        x0 = max(0, int(min(xs)))
        x1 = min(size - 1, int(max(xs)))
        n = len(pts)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                px, py = x + 0.5, y + 0.5
                inside = False
                j = n - 1
                for i in range(n):
                    xi, yi = pts[i]
                    xj, yj = pts[j]
                    if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-9) + xi):
                        inside = not inside
                    j = i
                if inside:
                    blend_px(x, y, r, g, b, a)

    s = size / 64.0
    # Paleta medieval Requiem
    bg_dark = (22, 16, 30, 255)
    gold = (232, 185, 62, 255)
    gold_hi = (255, 224, 120, 255)
    crimson = (176, 28, 52, 255)
    royal_purple = (104, 42, 148, 255)
    ivory = (238, 228, 214, 255)
    shadow = (32, 22, 42, 255)

    # Medalhão de fundo com borda dourada
    fill_circle(32 * s, 32 * s, 30.5 * s, gold)
    fill_circle(32 * s, 32 * s, 28.5 * s, bg_dark)

    # Gola medieval pontuda (colarinho do bobo da corte)
    fill_poly([(14 * s, 45 * s), (22 * s, 54 * s), (28 * s, 47 * s),
               (32 * s, 56 * s), (36 * s, 47 * s), (42 * s, 54 * s), (50 * s, 45 * s),
               (42 * s, 42 * s), (22 * s, 42 * s)], gold)
    fill_poly([(16 * s, 44 * s), (22 * s, 51 * s), (28 * s, 45 * s),
               (32 * s, 53 * s), (36 * s, 45 * s), (42 * s, 51 * s), (48 * s, 44 * s),
               (41 * s, 42 * s), (23 * s, 42 * s)], crimson)

    # Rosto / Máscara teatral dividida
    fill_circle(32 * s, 34 * s, 12.5 * s, ivory)
    # Olhos mascarados pontudos e sorriso irônico
    fill_poly([(24 * s, 31 * s), (29 * s, 32.5 * s), (26.5 * s, 35 * s)], shadow)
    fill_poly([(40 * s, 31 * s), (35 * s, 32.5 * s), (37.5 * s, 35 * s)], shadow)
    fill_poly([(25 * s, 39 * s), (32 * s, 42.5 * s), (39 * s, 39 * s), (32 * s, 40.5 * s)], crimson)

    # Chifres/Pontas do chapéu de bobo da corte (esquerda carmesim, centro dourado, direita roxa)
    # Ponta esquerda
    fill_poly([(20 * s, 28 * s), (10 * s, 20 * s), (14 * s, 11 * s),
               (23 * s, 17 * s), (28 * s, 24 * s)], crimson)
    # Ponta direita
    fill_poly([(44 * s, 28 * s), (54 * s, 20 * s), (50 * s, 11 * s),
               (41 * s, 17 * s), (36 * s, 24 * s)], royal_purple)
    # Ponta central
    fill_poly([(24 * s, 25 * s), (32 * s, 7 * s), (40 * s, 25 * s)], crimson)
    fill_poly([(32 * s, 7 * s), (40 * s, 25 * s), (32 * s, 24 * s)], royal_purple)

    # Faixa dourada da coroa do chapéu
    fill_poly([(19 * s, 25 * s), (45 * s, 25 * s), (44 * s, 28.5 * s), (20 * s, 28.5 * s)], gold)

    # Guizos dourados nas 3 pontas
    for bx, by in ((13.5 * s, 11.5 * s), (32 * s, 7.5 * s), (50.5 * s, 11.5 * s)):
        fill_circle(bx, by, 3.2 * s, gold)
        fill_circle(bx - 0.8 * s, by - 0.8 * s, 1.1 * s, gold_hi)

    return bytes(pixels)


def generate_jester_ico(dest: Path) -> Path:
    """Gera um arquivo .ico multi-resolução (64x64 e 32x32) do bobo da corte medieval."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    sizes = [64, 32]
    entries = []
    blobs = []
    offset = 6 + 16 * len(sizes)

    for sz in sizes:
        rgba = _draw_jester_bitmap(sz)
        # BITMAPINFOHEADER (40 bytes) — altura dobrada (sz*2) por padrão do formato ICO
        bih = struct.pack("<IIIHHIIIIII", 40, sz, sz * 2, 1, 32, 0, len(rgba), 0, 0, 0, 0)
        and_stride = ((sz + 31) // 32) * 4
        and_mask = b"\x00" * (and_stride * sz)
        blob = bih + rgba + and_mask
        w_byte = sz if sz < 256 else 0
        entries.append(struct.pack("<BBBBHHII", w_byte, w_byte, 0, 0, 1, 32, len(blob), offset))
        blobs.append(blob)
        offset += len(blob)

    header = struct.pack("<HHH", 0, 1, len(sizes))
    dest.write_bytes(header + b"".join(entries) + b"".join(blobs))
    return dest


def resolve_app_icon() -> Path | None:
    """Procura requiem_jester.ico ao lado do executável, nos assets empacotados ou gera no cache."""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / DEFAULT_ICON_NAME)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / DEFAULT_ICON_NAME)
    else:
        candidates.append(Path(__file__).resolve().parent / DEFAULT_ICON_NAME)

    for c in candidates:
        if c.exists():
            return c

    cached_ico = APP_DATA_DIR / DEFAULT_ICON_NAME
    if not cached_ico.exists():
        generate_jester_ico(cached_ico)
    return cached_ico


# ============================================================================
# Config Persistente, GPU e Análise de Binários
# ============================================================================

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"optiscaler_tag": None, "extra_folders": []}


def save_config(cfg: dict) -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def detect_gpu_info() -> dict:
    info = {
        "name": "GPU Desconhecida",
        "vendor": "unknown",
        "supports_fsr4_native": False,
        "supports_fsr4_int8": False,
    }
    if sys.platform != "win32":
        return info
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        )
        gpus = [line.strip() for line in out.splitlines() if line.strip()]
        chosen = gpus[0] if gpus else "GPU Desconhecida"
        for g in gpus:
            if any(k in g.lower() for k in ("rtx", "gtx", "radeon rx", "arc ")):
                chosen = g
                break
        gl = chosen.lower()
        info["name"] = chosen
        if "amd" in gl or "radeon" in gl:
            info["vendor"] = "amd"
            if re.search(r"rx\s*90\d\d", gl):
                info["supports_fsr4_native"] = True
                info["supports_fsr4_int8"] = True
            elif re.search(r"rx\s*(7\d\d\d|6\d\d\d)", gl):
                info["supports_fsr4_int8"] = True
        elif "nvidia" in gl or "geforce" in gl or "rtx" in gl or "gtx" in gl:
            info["vendor"] = "nvidia"
        elif "intel" in gl or "arc" in gl:
            info["vendor"] = "intel"
    except Exception:
        pass
    return info


def inspect_pe_binary(exe_path: Path) -> dict:
    result = {"arch": "unknown", "api_hint": "Desconhecida"}
    try:
        with open(exe_path, "rb") as f:
            dos = f.read(64)
            if len(dos) < 64 or dos[:2] != b"MZ":
                return result
            pe_offset = struct.unpack("<I", dos[0x3C:0x40])[0]
            f.seek(pe_offset)
            if f.read(4) != b"PE\x00\x00":
                return result
            machine = struct.unpack("<H", f.read(2))[0]
            result["arch"] = "x64" if machine == 0x8664 else ("x86 (32-bit)" if machine == 0x014C else f"0x{machine:04X}")

        with open(exe_path, "rb") as f:
            chunk = f.read(12 * 1024 * 1024).lower()
        apis = []
        if b"d3d12.dll" in chunk:
            apis.append("DX12")
        if b"vulkan-1.dll" in chunk:
            apis.append("Vulkan")
        if b"d3d11.dll" in chunk:
            apis.append("DX11")
        if apis:
            result["api_hint"] = " / ".join(apis)
    except Exception:
        pass
    return result


def analyze_game_folder(game_root: Path, exe_path: Path) -> dict:
    exe_dir = exe_path.parent
    exe_name_lower = exe_path.name.lower()
    pe = inspect_pe_binary(exe_path)

    anti_cheat_found = []
    native_upscalers = []

    try:
        for root_dir in {game_root, exe_dir}:
            for p in root_dir.rglob("*"):
                if len(p.relative_to(root_dir).parts) > 3:
                    continue
                nl = p.name.lower()
                if any(ac in nl for ac in ANTICHEAT_MARKERS):
                    anti_cheat_found.append(p.name)
                if "nvngx_dlss" in nl:
                    native_upscalers.append("DLSS")
                elif "amd_fidelityfx" in nl or "ffx_fsr" in nl:
                    native_upscalers.append("FSR")
                elif "libxess" in nl:
                    native_upscalers.append("XeSS")
    except Exception:
        pass

    profile = GAME_PROFILES.get(exe_name_lower)
    return {
        "arch": pe["arch"],
        "api": profile["api"] if profile else pe["api_hint"],
        "anti_cheat": sorted(set(anti_cheat_found)),
        "native_upscalers": sorted(set(native_upscalers)),
        "installed": (exe_dir / MANIFEST_NAME).exists(),
        "profile": profile,
    }


# ============================================================================
# Descoberta de Jogos (Steam, Epic, Pastas Manuais)
# ============================================================================

def find_main_executable(game_dir: Path, game_title: str = "") -> Path | None:
    if not game_dir.exists():
        return None
    ignore_kw = (
        "crashreport", "crashhandler", "unins", "setup", "prereq",
        "redist", "vcredist", "dxsetup", "dotnet", "easyanticheat",
        "battleye", "launcher", "config", "updater", "benchmark",
    )

    ue_exes = list(game_dir.rglob("*-Win64-Shipping.exe"))
    if ue_exes:
        return max(ue_exes, key=lambda p: p.stat().st_size)

    candidates = []
    for p in game_dir.rglob("*.exe"):
        rel_parts = p.relative_to(game_dir).parts
        if len(rel_parts) > 4:
            continue
        nl = p.name.lower()
        if any(bad in nl for bad in ignore_kw):
            continue
        if any(bad in str(p.parent).lower() for bad in ("_commonredist", "redist", "engine\\binaries")):
            continue
        try:
            score = p.stat().st_size / (1024 * 1024)
            if len(rel_parts) == 1:
                score += 50
            if game_title:
                ct = re.sub(r"[^a-z0-9]", "", game_title.lower())
                ce = re.sub(r"[^a-z0-9]", "", p.stem.lower())
                if ce and ce in ct:
                    score += 100
            candidates.append((score, p))
        except OSError:
            continue

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def discover_steam_games() -> list[dict]:
    games = []
    if not winreg:
        return games
    steam_path = None
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for subkey in (r"Software\Valve\Steam", r"Software\WOW6432Node\Valve\Steam"):
            try:
                with winreg.OpenKey(root, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, "SteamPath")
                    if val and Path(val).exists():
                        steam_path = Path(val)
                        break
            except OSError:
                continue
        if steam_path:
            break

    if not steam_path:
        return games

    libraries = {steam_path}
    vdf = steam_path / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        text = vdf.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            lib = Path(m.group(1).replace("\\\\", "\\"))
            if lib.exists():
                libraries.add(lib)

    for lib in libraries:
        sa = lib / "steamapps"
        if not sa.exists():
            continue
        for acf in sa.glob("appmanifest_*.acf"):
            try:
                txt = acf.read_text(encoding="utf-8", errors="ignore")
                nm = re.search(r'"name"\s+"([^"]+)"', txt)
                dm = re.search(r'"installdir"\s+"([^"]+)"', txt)
                if not (nm and dm):
                    continue
                name = nm.group(1)
                if "steamworks common redistributables" in name.lower():
                    continue
                install_dir = sa / "common" / dm.group(1)
                exe = find_main_executable(install_dir, name)
                if exe:
                    games.append({"title": name, "platform": "Steam", "root": install_dir, "exe": exe})
            except Exception:
                continue
    return games


def discover_epic_games() -> list[dict]:
    games = []
    mdir = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    if not mdir.exists():
        return games
    for item in mdir.glob("*.item"):
        try:
            data = json.loads(item.read_text(encoding="utf-8", errors="ignore"))
            name, loc = data.get("DisplayName"), data.get("InstallLocation")
            if not name or not loc:
                continue
            install_dir = Path(loc)
            exe = find_main_executable(install_dir, name)
            if exe:
                games.append({"title": name, "platform": "Epic", "root": install_dir, "exe": exe})
        except Exception:
            continue
    return games


def discover_all_games(extra_folders: list[Path] | None = None) -> list[dict]:
    all_games, seen = [], set()
    for g in discover_steam_games() + discover_epic_games():
        k = str(g["exe"]).lower()
        if k not in seen:
            seen.add(k)
            all_games.append(g)

    for folder in (extra_folders or []):
        if not folder.exists():
            continue
        direct_exe = find_main_executable(folder, folder.name)
        if direct_exe and str(direct_exe).lower() not in seen:
            seen.add(str(direct_exe).lower())
            all_games.append({"title": folder.name, "platform": "Manual", "root": folder, "exe": direct_exe})
            continue
        for sub in folder.iterdir():
            if sub.is_dir():
                exe = find_main_executable(sub, sub.name)
                if exe and str(exe).lower() not in seen:
                    seen.add(str(exe).lower())
                    all_games.append({"title": sub.name, "platform": "Manual", "root": sub, "exe": exe})

    all_games.sort(key=lambda x: x["title"].lower())
    return all_games


# ============================================================================
# Atualização Automática (OptiScaler + Auto-Updater do Requiem Upscaler)
# ============================================================================

def _parse_version(ver: str) -> tuple[int, ...]:
    nums = [int(n) for n in re.findall(r"\d+", ver)]
    return tuple(nums) if nums else (0,)


def _github_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "RequiemUpscaler/1.0", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_latest_optiscaler_release() -> tuple[str, str, str]:
    data = _github_json(OPTISCALER_API)
    tag = data.get("tag_name", "latest")
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.lower().endswith((".7z", ".zip")) and "source" not in name.lower():
            return tag, name, asset["browser_download_url"]
    raise RuntimeError("Nenhum pacote .7z/.zip encontrado na release mais recente do OptiScaler.")


def check_app_self_update() -> dict | None:
    if not APP_GITHUB_REPO or APP_GITHUB_REPO.startswith("SEU_USUARIO"):
        return None
    url = f"https://api.github.com/repos/{APP_GITHUB_REPO}/releases/latest"
    data = _github_json(url)
    tag = data.get("tag_name", "0.0.0")
    if _parse_version(tag) <= _parse_version(APP_VERSION):
        return None
    for asset in data.get("assets", []):
        if asset.get("name", "").lower().endswith(".exe"):
            return {
                "tag": tag,
                "name": asset["name"],
                "url": asset["browser_download_url"],
            }
    return None


def download_file(url: str, dest: Path, progress_cb=None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "RequiemUpscaler/1.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total > 0:
                    progress_cb(int(downloaded * 100 / total))
    return dest


def apply_self_update_and_restart(new_exe_path: Path) -> None:
    """Substitui o .exe em execução usando um script .bat temporário e reabre o app."""
    current_exe = Path(sys.executable)
    bat_path = Path(tempfile.gettempdir()) / "requiem_self_update.bat"
    script = (
        "@echo off\n"
        "timeout /t 2 /nobreak >nul\n"
        f'move /y "{new_exe_path}" "{current_exe}" >nul\n'
        f'start "" "{current_exe}"\n'
        f'del "%~f0"\n'
    )
    bat_path.write_text(script, encoding="utf-8")
    subprocess.Popen(["cmd", "/c", str(bat_path)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# ============================================================================
# Extração, Manipulação de INI e Injeção Transacional
# ============================================================================

def find_7z_executable() -> str | None:
    for cand in (
        shutil.which("7z"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ):
        if cand and Path(cand).exists():
            return cand
    return None


def extract_archive(archive_path: Path, dest_dir: Path) -> None:
    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)

    ext = archive_path.suffix.lower()
    if ext == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(dest_dir)
        return

    if ext == ".7z":
        seven_z = find_7z_executable()
        if seven_z:
            subprocess.check_call([seven_z, "x", str(archive_path), f"-o{dest_dir}", "-y"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

        tar_exe = shutil.which("tar")
        if tar_exe:
            try:
                subprocess.check_call([tar_exe, "-xf", str(archive_path), "-C", str(dest_dir)],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except subprocess.CalledProcessError:
                pass

        try:
            import py7zr  # type: ignore
            with py7zr.SevenZipFile(archive_path, mode="r") as z:
                z.extractall(path=dest_dir)
            return
        except ImportError:
            pass

        raise RuntimeError(
            "Não foi possível extrair o arquivo .7z.\n"
            "Instale o 7-Zip ou inclua 'py7zr' ao compilar o executável."
        )
    raise RuntimeError(f"Formato não suportado: {ext}")


def update_ini_preserve_comments(ini_path: Path, updates: dict[str, dict[str, str]]) -> None:
    lines = ini_path.read_text(encoding="utf-8", errors="ignore").splitlines() if ini_path.exists() else []
    pending = {sec: dict(kvs) for sec, kvs in updates.items()}
    new_lines = []
    current_section = None

    def flush(sec_name: str):
        if sec_name in pending and pending[sec_name]:
            for k, v in pending[sec_name].items():
                new_lines.append(f"{k}={v}")
            pending[sec_name].clear()

    for line in lines:
        st = line.strip()
        if st.startswith("[") and st.endswith("]"):
            if current_section:
                flush(current_section)
            current_section = st[1:-1].strip()
            new_lines.append(line)
            continue
        if current_section and current_section in pending and not st.startswith(";") and "=" in st:
            key = st.split("=", 1)[0].strip()
            mk = next((pk for pk in pending[current_section] if pk.lower() == key.lower()), None)
            if mk:
                new_lines.append(f"{mk}={pending[current_section].pop(mk)}")
                continue
        new_lines.append(line)

    if current_section:
        flush(current_section)

    for sec, kvs in pending.items():
        if kvs:
            new_lines.extend(["", f"[{sec}]"])
            for k, v in kvs.items():
                new_lines.append(f"{k}={v}")

    ini_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def find_payload_root(extracted_dir: Path) -> Path:
    for p in extracted_dir.rglob("OptiScaler.dll"):
        return p.parent
    raise RuntimeError("OptiScaler.dll não encontrada dentro do pacote extraído.")


def choose_proxy_name(exe_dir: Path, preferred: str | None = None) -> str:
    if preferred and not (exe_dir / preferred).exists():
        return preferred
    for cand in PROXY_CANDIDATES:
        if not (exe_dir / cand).exists():
            return cand
    return "dxgi.dll"


def install_to_game(
    exe_path: Path,
    payload_root: Path,
    options: dict,
    bridge_archive: Path | None = None,
) -> dict:
    exe_dir = exe_path.parent
    manifest_path = exe_dir / MANIFEST_NAME
    if manifest_path.exists():
        raise RuntimeError("Já existe uma injeção ativa do Requiem Upscaler neste jogo. Remova antes de reinstalar.")

    backup_dir = exe_dir / BACKUP_DIR_NAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    installed_files, backed_up_files, created_dirs = [], [], []

    def copy_with_backup(src: Path, dst: Path):
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            rel = dst.relative_to(exe_dir)
            bkp = backup_dir / rel
            bkp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, bkp)
            backed_up_files.append(str(rel))
        shutil.copy2(src, dst)
        installed_files.append(str(dst.relative_to(exe_dir)))

    proxy_name = options.get("proxy_name") or choose_proxy_name(exe_dir)
    skip_files = {"setup_windows.bat", "setup_linux.sh", "optiscaler.dll"}

    for item in payload_root.iterdir():
        if item.name.lower() in skip_files:
            continue
        if item.is_file():
            copy_with_backup(item, exe_dir / item.name)
        elif item.is_dir():
            target_sub = exe_dir / item.name
            if not target_sub.exists():
                created_dirs.append(str(target_sub.relative_to(exe_dir)))
            for sub_file in item.rglob("*"):
                if sub_file.is_file():
                    copy_with_backup(sub_file, exe_dir / sub_file.relative_to(payload_root))

    copy_with_backup(payload_root / "OptiScaler.dll", exe_dir / proxy_name)

    bridge_installed = False
    if bridge_archive and bridge_archive.exists():
        bridge_tmp = CACHE_DIR / "bridge_tmp"
        extract_archive(bridge_archive, bridge_tmp)
        for bf in bridge_tmp.rglob("*"):
            if bf.is_file():
                bn = bf.name.lower()
                if bn in ("dxgi.dll", "reshade64.dll") and "reshade" in str(bf).lower():
                    copy_with_backup(bf, exe_dir / "ReShade64.dll")
                else:
                    copy_with_backup(bf, exe_dir / bf.name)
        shutil.rmtree(bridge_tmp, ignore_errors=True)
        bridge_installed = True

    upscaler_mode = options["upscaler"]
    fg_mode = options["framegen"]
    is_dx11 = "DX11" in options.get("api", "") and "DX12" not in options.get("api", "")

    ini_updates: dict[str, dict[str, str]] = {
        "Upscalers": {}, "FrameGen": {}, "Spoofing": {},
        "OptiScaler": {}, "FSR": {}, "OptiFG": {},
    }

    if upscaler_mode == "fsr4":
        ini_updates["Upscalers"]["Dx12Upscaler"] = "ffx"
        ini_updates["Upscalers"]["Dx11Upscaler"] = "fsr31_12" if is_dx11 else "auto"
        ini_updates["Upscalers"]["VulkanUpscaler"] = "ffx"
        ini_updates["FSR"]["Fsr4Update"] = "true"
        ini_updates["FSR"]["FsrAgilitySDKUpgrade"] = "true"
    elif upscaler_mode == "fsr31":
        ini_updates["Upscalers"]["Dx12Upscaler"] = "ffx"
        ini_updates["Upscalers"]["Dx11Upscaler"] = "fsr31_12" if is_dx11 else "fsr31"
        ini_updates["Upscalers"]["VulkanUpscaler"] = "ffx"
        ini_updates["FSR"]["Fsr4Update"] = "false"
    else:
        ini_updates["Upscalers"]["Dx12Upscaler"] = "auto"
        ini_updates["Upscalers"]["Dx11Upscaler"] = "auto"

    if fg_mode != "none":
        ini_updates["FrameGen"]["FGType"] = fg_mode

    # Aplica overrides do Preset selecionado e do Perfil específico do jogo
    for source_dict in (options.get("preset_ini") or {}, (options.get("profile") or {}).get("ini_overrides") or {}):
        for sec, kvs in source_dict.items():
            ini_updates.setdefault(sec, {}).update(kvs)

    if bridge_installed:
        ini_updates["OptiScaler"]["LoadReshade"] = "true"
        ini_updates["Spoofing"]["Dxgi"] = "false"

    ini_path = exe_dir / "OptiScaler.ini"
    if not ini_path.exists():
        installed_files.append("OptiScaler.ini")
    update_ini_preserve_comments(ini_path, ini_updates)

    manifest = {
        "installed_at": datetime.now().isoformat(),
        "game_exe": exe_path.name,
        "proxy_dll": proxy_name,
        "upscaler": upscaler_mode,
        "framegen": fg_mode,
        "preset": options.get("preset_name", "Custom"),
        "installed_files": sorted(set(installed_files)),
        "backed_up_files": sorted(set(backed_up_files)),
        "created_dirs": sorted(set(created_dirs)),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def uninstall_from_game(exe_path: Path) -> None:
    exe_dir = exe_path.parent
    manifest_path = exe_dir / MANIFEST_NAME
    backup_dir = exe_dir / BACKUP_DIR_NAME
    if not manifest_path.exists():
        raise RuntimeError("Nenhum manifesto do Requiem Upscaler encontrado nesta pasta.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for rel in manifest.get("installed_files", []):
        target = exe_dir / rel
        if target.exists():
            try:
                target.unlink()
            except OSError:
                pass

    for rel in manifest.get("backed_up_files", []):
        bkp = backup_dir / rel
        target = exe_dir / rel
        if bkp.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(bkp), str(target))

    for rel_dir in sorted(manifest.get("created_dirs", []), reverse=True):
        d = exe_dir / rel_dir
        if d.exists() and d.is_dir():
            try:
                shutil.rmtree(d)
            except OSError:
                pass

    if backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)
    manifest_path.unlink(missing_ok=True)


# ============================================================================
# Interface Gráfica — Tema Requiem (Carmesim / Roxo Real / Dourado)
# ============================================================================

class RequiemUpscalerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1100x720")
        self.root.minsize(960, 620)
        self.root.configure(bg="#15101b")

        ico = resolve_app_icon()
        if ico and ico.exists():
            try:
                self.root.iconbitmap(str(ico))
            except Exception:
                pass

        self.config = load_config()
        self.gpu_info = detect_gpu_info()
        self.games: list[dict] = []
        self.extra_folders: list[Path] = [Path(p) for p in self.config.get("extra_folders", []) if Path(p).exists()]
        self.selected_game: dict | None = None
        self.selected_analysis: dict | None = None
        self.custom_optiscaler_archive: Path | None = None
        self.bridge_archive: Path | None = None

        self._setup_styles()
        self._build_ui()
        self.refresh_games_async()
        self.check_updates_async(silent=True)

    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        bg = "#15101b"
        panel = "#1f1729"
        fg = "#efe8f5"
        gold = "#e8b93e"
        crimson = "#b01c34"

        style.configure(".", background=bg, foreground=fg, fieldbackground="#281e36", bordercolor="#3b2b52")
        style.configure("TFrame", background=bg)
        style.configure("TLabelframe", background=panel, foreground=gold, bordercolor="#473361")
        style.configure("TLabelframe.Label", background=panel, foreground=gold, font=("Segoe UI", 9, "bold"))
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("Panel.TLabel", background=panel, foreground=fg)
        style.configure("Warn.TLabel", background=panel, foreground="#ff6b7a", font=("Segoe UI", 9, "bold"))
        style.configure("TButton", background="#322347", foreground=fg, padding=(10, 5))
        style.map("TButton", background=[("active", "#4b356b")])
        style.configure("Accent.TButton", background=crimson, foreground="#ffffff", font=("Segoe UI", 9, "bold"), padding=(12, 6))
        style.map("Accent.TButton", background=[("active", "#d42442")])
        style.configure("Treeview", background="#1a1323", fieldbackground="#1a1323", foreground=fg, rowheight=24)
        style.configure("Treeview.Heading", background="#2b1f3a", foreground=gold, font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#57286e")])
        style.configure("TProgressbar", troughcolor="#251c33", background=gold)

    def _build_ui(self):
        # Cabeçalho Requiem
        header = ttk.Frame(self.root, padding=(12, 10))
        header.pack(fill=tk.X)

        title_lbl = ttk.Label(
            header,
            text=f"✦ {APP_NAME} v{APP_VERSION}",
            font=("Segoe UI", 14, "bold"),
            foreground="#e8b93e",
        )
        title_lbl.pack(side=tk.LEFT)

        gpu_tag = (
            "FSR 4 Nativo" if self.gpu_info["supports_fsr4_native"]
            else ("FSR 4 INT8 / FSR 3.1" if self.gpu_info["supports_fsr4_int8"] else "FSR 3.1 / Frame Gen")
        )
        ttk.Label(
            header,
            text=f"   |   GPU: {self.gpu_info['name']} [{gpu_tag}]",
            font=("Segoe UI", 9),
            foreground="#c8bad8",
        ).pack(side=tk.LEFT)

        ttk.Button(header, text="Verificar Atualizações", command=lambda: self.check_updates_async(silent=False)).pack(side=tk.RIGHT, padx=4)
        ttk.Button(header, text="Adicionar Pasta", command=self.add_custom_folder).pack(side=tk.RIGHT, padx=4)
        ttk.Button(header, text="Reescanear", command=self.refresh_games_async).pack(side=tk.RIGHT, padx=4)

        # Corpo dividido
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        left_frame = ttk.Labelframe(paned, text="Jogos Detectados", padding=8)
        paned.add(left_frame, weight=2)

        srow = ttk.Frame(left_frame)
        srow.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(srow, text="Buscar:", style="Panel.TLabel").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.populate_tree())
        ttk.Entry(srow, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        self.tree = ttk.Treeview(left_frame, columns=("title", "platform", "status"), show="headings", selectmode="browse")
        self.tree.heading("title", text="Jogo")
        self.tree.heading("platform", text="Origem")
        self.tree.heading("status", text="Status")
        self.tree.column("title", width=270)
        self.tree.column("platform", width=80, anchor=tk.CENTER)
        self.tree.column("status", width=95, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_game_select)

        right_frame = ttk.Labelframe(paned, text="Perfil, Tecnologias & Injeção", padding=12)
        paned.add(right_frame, weight=3)

        self.info_label = ttk.Label(
            right_frame,
            text="Selecione um jogo na lista ao lado para visualizar o perfil e injetar.",
            wraplength=540, justify=tk.LEFT, style="Panel.TLabel",
        )
        self.info_label.pack(fill=tk.X, pady=(0, 8))

        self.warn_label = ttk.Label(right_frame, text="", wraplength=540, justify=tk.LEFT, style="Warn.TLabel")
        self.warn_label.pack(fill=tk.X, pady=(0, 8))

        # Presets Pré-Configurados
        opts = ttk.Labelframe(right_frame, text="Perfis Pré-Configurados & Tecnologias", padding=10)
        opts.pack(fill=tk.X, pady=6)

        ttk.Label(opts, text="Preset Rápido:", style="Panel.TLabel").grid(row=0, column=0, sticky=tk.W, pady=4)
        default_preset = "Qualidade Máxima — FSR 4 + OptiFG" if self.gpu_info["supports_fsr4_native"] else "Automático (Detectar GPU)"
        self.preset_var = tk.StringVar(value=default_preset)
        preset_cb = ttk.Combobox(opts, textvariable=self.preset_var, state="readonly", values=list(PRESET_PROFILES.keys()), width=44)
        preset_cb.grid(row=0, column=1, sticky=tk.W, padx=8, pady=4)
        preset_cb.bind("<<ComboboxSelected>>", self.on_preset_changed)

        ttk.Label(opts, text="Upscaler:", style="Panel.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.upscaler_var = tk.StringVar(value=PRESET_PROFILES[default_preset]["upscaler"])
        ttk.Combobox(opts, textvariable=self.upscaler_var, state="readonly", values=["fsr31", "fsr4", "auto"], width=22).grid(row=1, column=1, sticky=tk.W, padx=8, pady=4)

        ttk.Label(opts, text="Frame Generation:", style="Panel.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.fg_var = tk.StringVar(value=PRESET_PROFILES[default_preset]["framegen"])
        ttk.Combobox(opts, textvariable=self.fg_var, state="readonly", values=["optifg", "nukems", "xefg", "none"], width=22).grid(row=2, column=1, sticky=tk.W, padx=8, pady=4)

        ttk.Label(opts, text="Proxy DLL:", style="Panel.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.proxy_var = tk.StringVar(value="")
        ttk.Combobox(opts, textvariable=self.proxy_var, values=["", *PROXY_CANDIDATES], width=22).grid(row=3, column=1, sticky=tk.W, padx=8, pady=4)

        # Fontes & Bridge DX11
        pkg = ttk.Labelframe(right_frame, text="Motor OptiScaler & Bridge DX11", padding=10)
        pkg.pack(fill=tk.X, pady=6)

        cached_tag = self.config.get("optiscaler_tag") or "Será baixado automaticamente"
        self.opti_pkg_label = ttk.Label(pkg, text=f"OptiScaler (Auto-Update): {cached_tag}", style="Panel.TLabel")
        self.opti_pkg_label.pack(anchor=tk.W)
        ttk.Button(pkg, text="Usar .7z/.zip local do OptiScaler (Opcional)", command=self.pick_optiscaler_archive).pack(anchor=tk.W, pady=(3, 8))

        self.bridge_pkg_label = ttk.Label(pkg, text="Bridge DX11 (Opcional p/ Sekiro & DS3): Nenhum selecionado", wraplength=520, style="Panel.TLabel")
        self.bridge_pkg_label.pack(anchor=tk.W)
        ttk.Button(pkg, text="Selecionar Bridge DX11 (.zip/.7z — SekiroTSR / DS3 Upscaler)", command=self.pick_bridge_archive).pack(anchor=tk.W, pady=(3, 0))

        # Ações
        brow = ttk.Frame(right_frame)
        brow.pack(fill=tk.X, pady=10)
        self.install_btn = ttk.Button(brow, text="Injetar Requiem Upscaler", style="Accent.TButton", command=self.start_install)
        self.install_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.uninstall_btn = ttk.Button(brow, text="Remover / Restaurar Original", command=self.start_uninstall)
        self.uninstall_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(brow, text="Abrir Pasta", command=self.open_game_folder).pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(right_frame, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, pady=(2, 6))

        self.log_text = tk.Text(right_frame, height=8, state=tk.DISABLED, bg="#110c16", fg="#dfd5eb", font=("Consolas", 8))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, msg: str):
        def _append():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.root.after(0, _append)

    def on_preset_changed(self, _event=None):
        p = PRESET_PROFILES.get(self.preset_var.get())
        if p:
            self.upscaler_var.set(p["upscaler"])
            self.fg_var.set(p["framegen"])

    def check_updates_async(self, silent: bool = True):
        def worker():
            # 1) Auto-Update do Motor OptiScaler
            try:
                tag, asset_name, url = fetch_latest_optiscaler_release()
                current_tag = self.config.get("optiscaler_tag")
                archive_path = ARCHIVE_DIR / asset_name
                if tag != current_tag or not archive_path.exists():
                    self.log(f"Nova versão do OptiScaler encontrada ({tag}). Baixando automaticamente...")
                    download_file(url, archive_path, lambda p: self.root.after(0, lambda v=p: self.progress.configure(value=v)))
                    extract_target = EXTRACTED_DIR / re.sub(r"[^a-zA-Z0-9._-]", "_", tag)
                    extract_archive(archive_path, extract_target)
                    self.config["optiscaler_tag"] = tag
                    self.config["optiscaler_archive"] = str(archive_path)
                    save_config(self.config)
                    self.root.after(0, lambda t=tag: (
                        self.opti_pkg_label.config(text=f"OptiScaler (Auto-Update): {t} [Atualizado]"),
                        self.progress.configure(value=0),
                    ))
                    self.log(f"Motor OptiScaler atualizado para {tag}.")
                elif not silent:
                    self.log(f"OptiScaler já está na versão mais recente ({tag}).")
            except Exception as exc:
                if not silent:
                    self.log(f"Aviso ao verificar OptiScaler: {exc}")

            # 2) Auto-Update do próprio Requiem Upscaler.exe
            try:
                upd = check_app_self_update()
                if upd:
                    self.log(f"Nova versão do {APP_NAME} disponível: {upd['tag']}!")
                    def ask_and_update():
                        if not getattr(sys, "frozen", False):
                            messagebox.showinfo("Atualização Disponível", f"Nova versão {upd['tag']} disponível no GitHub!")
                            return
                        if messagebox.askyesno("Atualização Automática", f"Deseja atualizar o {APP_NAME} para a versão {upd['tag']} agora?"):
                            self._run_self_update(upd)
                    self.root.after(0, ask_and_update)
                elif not silent:
                    self.log(f"{APP_NAME} v{APP_VERSION} está atualizado.")
            except Exception as exc:
                if not silent:
                    self.log(f"Aviso ao verificar atualização do app: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _run_self_update(self, upd: dict):
        def worker():
            try:
                tmp_exe = Path(tempfile.gettempdir()) / f"RequiemUpscaler_{upd['tag']}.exe"
                self.log(f"Baixando atualização {upd['tag']}...")
                download_file(upd["url"], tmp_exe, lambda p: self.root.after(0, lambda v=p: self.progress.configure(value=v)))
                apply_self_update_and_restart(tmp_exe)
                self.root.after(0, self.root.destroy)
            except Exception as exc:
                self.log(f"Falha na auto-atualização: {exc}")
        threading.Thread(target=worker, daemon=True).start()

    def refresh_games_async(self):
        self.log("Escaneando jogos (Steam, Epic e pastas adicionadas)...")
        def worker():
            found = discover_all_games(self.extra_folders)
            self.root.after(0, lambda: self._on_games_loaded(found))
        threading.Thread(target=worker, daemon=True).start()

    def _on_games_loaded(self, found: list[dict]):
        self.games = found
        self.populate_tree()
        self.log(f"{len(found)} jogo(s) encontrado(s).")

    def populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        q = self.search_var.get().strip().lower()
        for idx, g in enumerate(self.games):
            if q and q not in g["title"].lower():
                continue
            status = "Injetado" if (g["exe"].parent / MANIFEST_NAME).exists() else "Original"
            self.tree.insert("", tk.END, iid=str(idx), values=(g["title"], g["platform"], status))

    def add_custom_folder(self):
        folder = filedialog.askdirectory(title="Selecione a pasta de um jogo ou biblioteca")
        if not folder:
            return
        p = Path(folder)
        if p not in self.extra_folders:
            self.extra_folders.append(p)
            self.config["extra_folders"] = [str(f) for f in self.extra_folders]
            save_config(self.config)
        self.refresh_games_async()

    def pick_optiscaler_archive(self):
        f = filedialog.askopenfilename(title="Selecionar OptiScaler (.7z ou .zip)", filetypes=[("Compactados", "*.7z *.zip")])
        if f:
            self.custom_optiscaler_archive = Path(f)
            self.opti_pkg_label.config(text=f"OptiScaler local: {self.custom_optiscaler_archive.name}")

    def pick_bridge_archive(self):
        f = filedialog.askopenfilename(title="Selecionar Bridge DX11 (.zip ou .7z)", filetypes=[("Compactados", "*.zip *.7z")])
        if f:
            self.bridge_archive = Path(f)
            self.bridge_pkg_label.config(text=f"Bridge DX11: {self.bridge_archive.name}")

    def on_game_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        g = self.games[int(sel[0])]
        self.selected_game = g
        analysis = analyze_game_folder(g["root"], g["exe"])
        self.selected_analysis = analysis

        ups_str = ", ".join(analysis["native_upscalers"]) if analysis["native_upscalers"] else "Nenhum detectado"
        self.info_label.config(text=(
            f"Jogo: {g['title']}   |   Status: {'INJETADO' if analysis['installed'] else 'Original'}\n"
            f"Executável: {g['exe'].name} ({analysis['arch']})   |   API: {analysis['api']}\n"
            f"Upscalers Nativos: {ups_str}\n"
            f"Pasta: {g['exe'].parent}"
        ))

        warnings = []
        if analysis["anti_cheat"]:
            warnings.append(f"ALERTA ANTI-CHEAT ({', '.join(analysis['anti_cheat'])}): NÃO injete em modo online para evitar banimento!")
        if analysis["arch"] != "x64":
            warnings.append("Executável não é 64-bit. OptiScaler/FSR3.1/FSR4 exigem jogos 64-bit.")

        prof = analysis["profile"]
        if prof:
            warnings.append(prof["notes"])
            self.proxy_var.set(prof["recommended_proxy"])
            if prof.get("preset_hint") in PRESET_PROFILES:
                self.preset_var.set(prof["preset_hint"])
                self.on_preset_changed()
        else:
            self.proxy_var.set("")
            if not analysis["native_upscalers"]:
                warnings.append("Nenhum upscaler nativo (DLSS/FSR2/XeSS) encontrado. Jogos DX11 sem upscaler podem exigir um Bridge Addon.")

        self.warn_label.config(text="\n\n".join(warnings))

    def open_game_folder(self):
        if self.selected_game:
            os.startfile(str(self.selected_game["exe"].parent))

    def start_install(self):
        if not self.selected_game or not self.selected_analysis:
            messagebox.showwarning("Aviso", "Selecione um jogo primeiro.")
            return
        if self.selected_analysis["anti_cheat"]:
            if not messagebox.askyesno(
                "Alerta Anti-Cheat",
                f"Anti-cheat detectado ({', '.join(self.selected_analysis['anti_cheat'])}).\nContinuar mesmo assim?",
            ):
                return

        self.install_btn.config(state=tk.DISABLED)
        self.uninstall_btn.config(state=tk.DISABLED)
        self.progress["value"] = 10

        game = self.selected_game
        analysis = self.selected_analysis
        preset_name = self.preset_var.get()
        options = {
            "preset_name": preset_name,
            "preset_ini": PRESET_PROFILES.get(preset_name, {}).get("ini", {}),
            "upscaler": self.upscaler_var.get(),
            "framegen": self.fg_var.get(),
            "proxy_name": self.proxy_var.get().strip() or None,
            "api": analysis["api"],
            "profile": analysis["profile"],
        }
        custom_arc = self.custom_optiscaler_archive
        bridge_arc = self.bridge_archive

        def worker():
            try:
                if custom_arc and custom_arc.exists():
                    archive_path, tag = custom_arc, custom_arc.stem
                else:
                    tag = self.config.get("optiscaler_tag")
                    cached_arc = Path(self.config.get("optiscaler_archive", ""))
                    if not tag or not cached_arc.exists():
                        self.log("Baixando última release do OptiScaler...")
                        tag, asset_name, url = fetch_latest_optiscaler_release()
                        cached_arc = ARCHIVE_DIR / asset_name
                        download_file(url, cached_arc, lambda p: self.root.after(0, lambda v=p: self.progress.configure(value=v)))
                        self.config["optiscaler_tag"] = tag
                        self.config["optiscaler_archive"] = str(cached_arc)
                        save_config(self.config)
                    archive_path = cached_arc

                extract_target = EXTRACTED_DIR / re.sub(r"[^a-zA-Z0-9._-]", "_", tag)
                if not any(extract_target.rglob("OptiScaler.dll")):
                    self.log("Extraindo motor OptiScaler...")
                    extract_archive(archive_path, extract_target)

                payload_root = find_payload_root(extract_target)
                self.log(f"Aplicando perfil '{preset_name}' em {game['title']}...")
                manifest = install_to_game(game["exe"], payload_root, options, bridge_archive=bridge_arc)

                self.log(f"Injeção concluída! Proxy: {manifest['proxy_dll']} | Pressione INSERT no jogo para abrir o menu.")
                self.root.after(0, lambda: (
                    self.progress.configure(value=100),
                    self.populate_tree(),
                    self.on_game_select(),
                    messagebox.showinfo(
                        APP_NAME,
                        f"Injeção concluída para {game['title']}!\n"
                        f"Proxy DLL: {manifest['proxy_dll']}\n"
                        f"Perfil: {preset_name}\n\n"
                        "Abra o jogo e pressione INSERT para ajustar o menu in-game.",
                    ),
                ))
            except Exception as exc:
                self.log(f"ERRO: {exc}")
                self.root.after(0, lambda e=exc: messagebox.showerror("Erro", str(e)))
            finally:
                self.root.after(0, lambda: (
                    self.install_btn.config(state=tk.NORMAL),
                    self.uninstall_btn.config(state=tk.NORMAL),
                ))

        threading.Thread(target=worker, daemon=True).start()

    def start_uninstall(self):
        if not self.selected_game:
            return
        try:
            uninstall_from_game(self.selected_game["exe"])
            self.log(f"Arquivos removidos e pasta original restaurada ({self.selected_game['title']}).")
            self.populate_tree()
            self.on_game_select()
            messagebox.showinfo(APP_NAME, "Arquivos removidos e jogo restaurado ao estado original.")
        except Exception as exc:
            messagebox.showerror("Erro ao Remover", str(exc))


if __name__ == "__main__":
    if "--make-icon" in sys.argv:
        out_ico = Path(__file__).resolve().parent / DEFAULT_ICON_NAME
        generate_jester_ico(out_ico)
        print(f"Ícone gerado com sucesso: {out_ico}")
        sys.exit(0)

    root = tk.Tk()
    app = RequiemUpscalerApp(root)
    root.mainloop()
