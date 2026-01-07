import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from fpdf import FPDF
import base64
from datetime import datetime
import os
import io
import tempfile
from PIL import Image
import re
import unicodedata


# =============================
# AUTH (login interno) — MVP
# =============================
import hashlib
import hmac
import time

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _get_auth_cfg():
    """Lee configuración desde st.secrets (Streamlit Cloud)."""
    cfg = {
        "enabled": True,
        "session_ttl_minutes": 12 * 60,   # 12 horas
        "max_attempts": 8,
        "lockout_minutes": 5,
        "users": {}
    }

    try:
        if "auth" in st.secrets:
            s = st.secrets["auth"]
            cfg["enabled"] = bool(s.get("enabled", cfg["enabled"]))
            cfg["session_ttl_minutes"] = int(s.get("session_ttl_minutes", cfg["session_ttl_minutes"]))
            cfg["max_attempts"] = int(s.get("max_attempts", cfg["max_attempts"]))
            cfg["lockout_minutes"] = int(s.get("lockout_minutes", cfg["lockout_minutes"]))
            cfg["users"] = dict(s.get("users", {}))
    except Exception:
        pass

    return cfg

def _is_locked() -> bool:
    lock_until = st.session_state.get("_auth_lock_until", 0.0)
    return time.time() < float(lock_until)

def _register_failed_attempt(cfg):
    attempts = int(st.session_state.get("_auth_attempts", 0)) + 1
    st.session_state["_auth_attempts"] = attempts

    if attempts >= cfg["max_attempts"]:
        lock_seconds = int(cfg["lockout_minutes"]) * 60
        st.session_state["_auth_lock_until"] = time.time() + lock_seconds

def _reset_attempts():
    st.session_state["_auth_attempts"] = 0
    st.session_state["_auth_lock_until"] = 0.0

def _verify_password(plain_password: str, stored_sha256: str) -> bool:
    calc = _sha256(plain_password or "")
    return hmac.compare_digest(calc, stored_sha256 or "")

def require_login():
    """Gate de acceso: si no está autenticado, muestra login y detiene la app."""
    cfg = _get_auth_cfg()

    if not cfg["enabled"]:
        return

    # Sesión válida
    authed = bool(st.session_state.get("_auth_ok", False))
    auth_ts = float(st.session_state.get("_auth_ts", 0.0))
    ttl = int(cfg["session_ttl_minutes"]) * 60

    if authed and (time.time() - auth_ts) < ttl:
        with st.sidebar:
            if st.button("🔒 Cerrar sesión"):
                st.session_state["_auth_ok"] = False
                st.session_state["_auth_user"] = None
                st.session_state["_auth_role"] = None
                st.session_state["_auth_ts"] = 0.0
                st.rerun()
        return

    if _is_locked():
        st.error("Demasiados intentos. Intenta más tarde.")
        st.stop()

    st.title("🔐 Acceso privado")
    st.caption("Ingresa tus credenciales para continuar.")

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Usuario", placeholder="ej. jay").strip()
        password = st.text_input("Contraseña", type="password")
        submit = st.form_submit_button("Entrar")

    if not cfg["users"]:
        st.warning("Auth activo pero no hay usuarios configurados en Secrets. Configura [auth.users].")
        st.stop()

    if submit:
        user = cfg["users"].get(username)
        if not user:
            _register_failed_attempt(cfg)
            st.error("Usuario o contraseña incorrectos.")
            st.stop()

        stored = user.get("password_sha256", "")
        role = user.get("role", "viewer")

        if _verify_password(password, stored):
            _reset_attempts()
            st.session_state["_auth_ok"] = True
            st.session_state["_auth_user"] = username
            st.session_state["_auth_role"] = role
            st.session_state["_auth_ts"] = time.time()
            st.rerun()
        else:
            _register_failed_attempt(cfg)
            st.error("Usuario o contraseña incorrectos.")
            st.stop()

    st.stop()

# -----------------------------
# CONSTANTES FISCALES (MX) - MVP
# -----------------------------
TOPE_ART_151_ABS = 206_367.0  # Tope anual absoluto Art. 151 LISR (estimado, referencia)
TOPE_ART_185 = 152_000.0  # Tope anual Art. 185 LISR (estimado; ajustable según criterio/actualización)
FACTOR_CALIBRACION_ALLIANZ = 0.90  # Ajuste calibrado para replicar simulador Allianz en escenario Allianz-style



# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Simulador Krece360", layout="wide", page_icon="🛡️")

require_login()

# --- ESTILOS CSS ---
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
    }
    .stAlert {
        padding: 10px;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# --- NUEVA FUNCIÓN: MATRIZ DE COSTOS ALLIANZ (Pág 9 PDF) ---
def obtener_tasa_admin(aporte_mensual, plazo_anios):
    # Definir columna basada en el plazo (15, 20 o 25 años)
    if plazo_anios >= 25:
        col_idx = 2 
    elif plazo_anios >= 20:
        col_idx = 1 
    else:
        col_idx = 0 

    # Tabla: (Monto Mínimo, [Tasa 15, Tasa 20, Tasa 25])
    tabla_costos = [
        (10000, [0.0183, 0.0162, 0.0153]), 
        (7500,  [0.0187, 0.0165, 0.0156]), 
        (5000,  [0.0197, 0.0175, 0.0164]), 
        (4000,  [0.0206, 0.0181, 0.0169]), 
        (2500,  [0.0228, 0.0199, 0.0184]), 
        (0,     [0.0228, 0.0199, 0.0184])  # Default
    ]

    tasa_final = 0.0228 # Valor por defecto
    for monto_min, tasas in tabla_costos:
        if aporte_mensual >= monto_min:
            tasa_final = tasas[col_idx]
            break
            
    return tasa_final



# -----------------------------
# Helper: proyección rápida para comparar escenarios
# -----------------------------
def proyectar_saldo_final(
    ahorro_mensual: float,
    plazo_anos: int,
    edad: int,
    tasa_bruta_scenario: float,
    tasa_admin_real: float,
    inflacion: bool,
    tasa_inflacion: float,
    estrategia_fiscal: str,
    validar_sueldo: bool,
    sueldo_anual: float,
    isr_cliente: float,
    tope_art_151_abs: float,
    tope_art_185: float,
    reinvertir_beneficio: bool,
):
    tasa_neta = max(0.0, float(tasa_bruta_scenario) - float(tasa_admin_real))
    meses = int(plazo_anos) * 12
    saldo = 0.0
    aporte_actual = float(ahorro_mensual)

    if estrategia_fiscal == "Art 151 (PPR - Deducible)":
        tope_deducible_anual = float(tope_art_151_abs)
        if validar_sueldo:
            tope_deducible_anual = min(float(tope_art_151_abs), float(sueldo_anual) * 0.10)
    elif estrategia_fiscal == "Art 185 (Diferimiento)":
        tope_deducible_anual = float(tope_art_185)
    else:
        tope_deducible_anual = 0.0

    aporte_anual_real = 0.0

    saldo_al_fin_aportes = None
    for i in range(1, total_meses + 1):
        saldo += saldo * (tasa_neta / 12.0)
        saldo += aporte_actual
        aporte_anual_real += aporte_actual

        if i % 12 == 0:
            if tope_deducible_anual > 0:
                base_devolucion = min(aporte_anual_real, tope_deducible_anual)
                devolucion_anio = base_devolucion * float(isr_cliente)
                if reinvertir_beneficio:
                    saldo += devolucion_anio

            aporte_anual_real = 0.0
            if inflacion:
                aporte_actual *= (1.0 + float(tasa_inflacion))

    return saldo, tasa_neta


# --- CLASE PDF (PRODUCCIÓN) ---
class PDFReport(FPDF):
    def __init__(self, advisor_logo_path: str | None = None):
        super().__init__()
        self.advisor_logo_path = advisor_logo_path
        self.fecha_actual = datetime.now().strftime("%d/%m/%Y")

    # -----------------------------
    # Sanitización de texto (FPDF usa latin-1)
    # Evita errores tipo: 'latin-1' codec can't encode character '\u2014'
    # -----------------------------
    @staticmethod
    def _sanitize_pdf_text(s) -> str:
        if s is None:
            return ""
        s = str(s)

        replacements = {
            "—": "-",   # em dash —
            "–": "-",   # en dash –
            "−": "-",   # minus sign −
            "‘": "'",   # ‘
            "’": "'",   # ’
            "“": '"',   # “
            "”": '"',   # ”
            "•": "-",   # bullet •
            "\u00a0": " ",  # nbsp literal
            " ": " ",   # nbsp
        }
        for k, v in replacements.items():
            s = s.replace(k, v)

        s = unicodedata.normalize("NFKC", s)

        # Garantiza compatibilidad latin-1
        try:
            s.encode("latin-1")
            return s
        except Exception:
            return s.encode("latin-1", "replace").decode("latin-1")

    # Overwrite para proteger TODAS las impresiones
    def cell(self, w, h=0, txt="", border=0, ln=0, align="", fill=False, link=""):
        txt = self._sanitize_pdf_text(txt)
        return super().cell(w, h, txt, border, ln, align, fill, link)

    def multi_cell(self, w, h, txt="", border=0, align="J", fill=False):
        txt = self._sanitize_pdf_text(txt)
        return super().multi_cell(w, h, txt, border, align, fill)

    def header(self):
        # Logo del asesor (opcional) - esquina superior derecha
        if self.advisor_logo_path and os.path.exists(self.advisor_logo_path):
            try:
                # Ajusta tamaño si quieres
                self.image(self.advisor_logo_path, x=170, y=8, w=28)
            except Exception:
                pass

        # Título
        self.set_font("Arial", "B", 14)
        self.set_text_color(0, 0, 0)
        self.cell(0, 10, "Propuesta Personal de Retiro (PPR) - Simulacion estimada", 0, 1, "L")

        # Fecha
        self.set_font("Arial", "I", 10)
        self.set_text_color(80, 80, 80)
        self.cell(0, 6, f"Fecha: {self.fecha_actual}", 0, 1, "L")
        self.ln(4)
        self.set_text_color(0, 0, 0)

    def footer(self):
        # --- Footer compacto para evitar encimarse con el contenido ---
        # Dejamos un margen inferior amplio con set_auto_page_break(margin=28)
        # y aquí dibujamos un aviso legal corto + paginación.

        # Aviso legal (compacto)
        self.set_y(-24)
        self.set_font("Arial", "", 6)
        self.set_text_color(100, 100, 100)

        disclaimer = (
            "Aviso legal: Proyeccion informativa y estimativa. No constituye cotizacion formal ni oferta vinculante. "
            "Rendimientos no garantizados y pueden variar. Consulte a su asesor para cotizacion oficial."
        )
        self.multi_cell(0, 2.8, disclaimer, 0, "C")

        # Paginación (separada para que nunca se encime con el texto)
        self.set_y(-10)
        self.set_text_color(0, 0, 0)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Pagina {self.page_no()} | Generado con Simulador Krece360", 0, 0, "C")


# --- Helpers de endurecimiento (uploads / archivos) ---
def _safe_filename(text: str, default: str = "propuesta") -> str:
    try:
        text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    except Exception:
        text = str(text)
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_")
    return text or default

def _save_logo_to_temp(uploaded_file) -> str | None:
    """Guarda el logo subido en un archivo temporal seguro y devuelve la ruta."""
    if uploaded_file is None:
        return None
    # Límite (evita uploads gigantes)
    MAX_BYTES = 2 * 1024 * 1024  # 2MB
    data = uploaded_file.getvalue()
    if data is None:
        return None
    if len(data) > MAX_BYTES:
        raise ValueError("El logotipo excede 2MB. Sube una imagen más ligera.")
    # Validar tipo real de imagen (no solo extensión)
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # valida integridad
        fmt = (img.format or "").lower()
    except Exception:
        raise ValueError("El logotipo no es una imagen válida. Usa PNG o JPG/JPEG.")
    if fmt not in {"png", "jpeg", "jpg"}:
        raise ValueError("Formato de logotipo no soportado. Usa PNG o JPG/JPEG.")
    suffix = ".png" if fmt == "png" else ".jpg"
    fd, path = tempfile.mkstemp(prefix="k360_logo_", suffix=suffix)
    os.close(fd)
    with open(path, "wb") as f:
        f.write(data)
    return path

def _prepare_logo_for_pdf(logo_path: str | None) -> str | None:
    """Convierte el logo a JPG (RGB) con fondo blanco (si trae transparencia) para máxima compatibilidad con FPDF.
    Devuelve la ruta al JPG temporal.
    """
    if not logo_path or not os.path.exists(logo_path):
        return None
    try:
        img = Image.open(logo_path)

        # Si trae transparencia (RGBA/LA o paleta con transparencia), "aplanar" sobre fondo blanco.
        has_alpha = (
            img.mode in ("RGBA", "LA")
            or (img.mode == "P" and "transparency" in img.info)
        )

        if has_alpha:
            rgba = img.convert("RGBA")
            # Fondo blanco sólido
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            # Componer manteniendo alpha
            try:
                bg.alpha_composite(rgba)
                rgb = bg.convert("RGB")
            except Exception:
                # Fallback por si alpha_composite falla
                rgb_bg = Image.new("RGB", rgba.size, (255, 255, 255))
                rgb_bg.paste(rgba, mask=rgba.split()[-1])
                rgb = rgb_bg
        else:
            rgb = img.convert("RGB")

        fd, out_path = tempfile.mkstemp(prefix="k360_logo_pdf_", suffix=".jpg")
        os.close(fd)
        rgb.save(out_path, format="JPEG", quality=92, optimize=True)
        return out_path
    except Exception:
        # Si falla, intentamos usar el original (por si ya es compatible)
        return logo_path



def crear_pdf(datos_cliente, datos_fin, datos_fiscales, datos_asesor, ruta_logo_temp):
    try:
        logo_pdf_path = _prepare_logo_for_pdf(ruta_logo_temp)
        pdf = PDFReport(advisor_logo_path=logo_pdf_path)
        pdf.set_auto_page_break(auto=True, margin=34)
        pdf.add_page()
        
        # --- CORRECCIÓN ESPACIO LOGO ---
        pdf.ln(15) 
        
        pdf.set_font("Arial", size=12)
        
        # Datos Cliente
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, f"Propuesta para: {datos_cliente['nombre']}", 0, 1)
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, f"Edad Actual: {datos_cliente['edad']} | Edad Retiro: {datos_cliente['retiro']}", 0, 1)
        pdf.cell(0, 10, f"Estrategia: {datos_cliente['estrategia']}", 0, 1)
        pdf.ln(5)

        # Resumen de la estrategia
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, "Resumen de la estrategia", 0, 1)
        pdf.set_font("Arial", size=9)
        resumen = (
            "Con base en la información proporcionada, esta simulación presenta una proyección estimada "
            "de ahorro para el retiro mediante un Plan Personal de Retiro (PPR), considerando aportaciones "
            "periódicas, un horizonte de largo plazo y el tratamiento fiscal conforme a la legislación vigente. "
            "Los resultados son estimativos y no representan una garantía de rendimiento futuro."
        )
        pdf.multi_cell(0, 4.5, resumen)
        pdf.ln(2)

        # Resumen Financiero
        pdf.set_fill_color(240, 242, 246)
        y_actual = pdf.get_y()
        pdf.rect(10, y_actual, 190, 45, 'F') # Ajusté un poco la altura
        
        pdf.set_y(y_actual + 5)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"   Aportación Mensual: ${datos_fin['aporte_mensual']:,.2f}", 0, 1)
        pdf.cell(0, 10, f"   Total aportado estimado: ${datos_fin['total_aportado']:,.2f}", 0, 1)
        pdf.cell(0, 10, f"   Saldo Estimado al Retiro: ${datos_fin['saldo_final']:,.2f}", 0, 1)
        pdf.cell(0, 10, f"   Beneficio SAT Estimado: ${datos_fin['beneficio_sat']:,.2f}", 0, 1) # Aquí va el dato corregido
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 10, f"   (Tasa Admin Aplicada: {datos_fin['tasa_admin_pct']:.2f}%)", 0, 1)
        

        pdf.set_y(y_actual + 50)

        # Comparador de Escenarios (mini-tabla)
        comp = datos_fin.get('comparador') if isinstance(datos_fin, dict) else None
        if comp and isinstance(comp, list):
            try:
                pdf.ln(2)
                pdf.set_font("Arial", 'B', 11)
                pdf.cell(0, 8, "Comparación de escenarios (resumen):", 0, 1)

                # Encabezados
                pdf.set_font("Arial", 'B', 9)
                pdf.set_fill_color(240, 242, 246)
                pdf.set_draw_color(200, 200, 200)

                col1, col2, col3 = 85, 40, 55  # total 180 aprox dentro de márgenes
                pdf.cell(col1, 6, "Escenario", 1, 0, 'L', True)
                pdf.cell(col2, 6, "Tasa neta", 1, 0, 'C', True)
                pdf.cell(col3, 6, "Monto al retiro", 1, 1, 'R', True)

                pdf.set_font("Arial", size=9)

                # Filas (máximo 4 para no saturar)
                for r in comp[:4]:
                    esc = str(r.get('escenario', ''))
                    tasa = r.get('tasa_neta_pct', None)
                    monto = r.get('monto_retiro', None)

                    tasa_txt = f"{float(tasa):.2f}%" if tasa is not None else ""
                    monto_txt = f"${float(monto):,.0f}" if monto is not None else ""

                    pdf.cell(col1, 6, esc, 1, 0, 'L')
                    pdf.cell(col2, 6, tasa_txt, 1, 0, 'C')
                    pdf.cell(col3, 6, monto_txt, 1, 1, 'R')

                # Nota de calibración (solo si aplica)
                if any('Allianz-style' in str(x.get('escenario','')) for x in comp):
                    pdf.ln(1)
                    pdf.set_font("Arial", 'I', 7)
                    pdf.set_text_color(90, 90, 90)
                    pdf.multi_cell(0, 3.5, "Nota: El escenario Allianz-style incluye un ajuste de calibración para reflejar cargos y fricciones propias del producto comercial.")
                    pdf.set_text_color(0, 0, 0)

                pdf.ln(2)
                pdf.set_font("Arial", 'I', 9)
                pdf.multi_cell(
                    0, 4,
                    "Nota: El escenario optimista puede presentar mayor volatilidad. "
                    "El recomendado busca equilibrio entre crecimiento y control del riesgo."
                )
                pdf.ln(2)
            except Exception:
                pass

        # Análisis Fiscal

        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "Análisis fiscal simplificado:", 0, 1)
        pdf.set_font("Arial", size=11)
        pdf.multi_cell(0, 8, datos_fiscales['texto_analisis'])
        
        if datos_fiscales['alerta_excedente']:
            pdf.ln(5)
            pdf.set_text_color(200, 0, 0)
            pdf.multi_cell(0, 8, f"NOTA IMPORTANTE: {datos_fiscales['alerta_excedente']}")
            pdf.set_text_color(0, 0, 0)
            

        # Siguiente paso recomendado
        pdf.ln(6)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, "Siguiente paso recomendado", 0, 1)
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(
            0, 5,
            "Revisa esta proyección junto con tu asesor para validar si esta estrategia se ajusta a tus objetivos "
            "financieros, capacidad de ahorro y horizonte de inversión, y definir el siguiente paso hacia una "
            "cotización oficial y proceso de contratación."
        )

        # Firma Asesor
        pdf.ln(15)
        pdf.set_draw_color(150, 150, 150)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y()) 
        pdf.ln(5)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "Asesor Certificado:", 0, 1)
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 8, f"{datos_asesor['nombre']}", 0, 1)
        pdf.cell(0, 8, f"Contacto: {datos_asesor['telefono']}", 0, 1)

        pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')

        # Limpieza de logo convertido (si aplica)
        try:
            if logo_pdf_path and ruta_logo_temp and os.path.exists(logo_pdf_path) and (logo_pdf_path != ruta_logo_temp):
                os.remove(logo_pdf_path)
        except Exception:
            pass

        return pdf_bytes, None
    except Exception as e:
        return None, str(e)

# --- 1. SIDEBAR ---
with st.sidebar:
    st.image("https://via.placeholder.com/150x50?text=Logo+Krece360", use_column_width=True) 
    st.header("⚙️ Parámetros")
    
    st.subheader("Datos del Prospecto")
    nombre = st.text_input("Nombre Cliente", value="Juan Pérez")
    
    st.subheader("Configuración Plan")
    col_edad, col_fin, col_obj = st.columns(3)
edad = col_edad.number_input("Edad", value=30, step=1)
edad_fin_aportes = col_fin.number_input("Fin de aportaciones (edad)", value=55, step=1, help="Edad a la que dejas de aportar (plazo comprometido).")
retiro = col_obj.number_input("Edad objetivo (retiro real)", value=65, step=1, help="Edad a la que quieres ver el saldo (puede ser mayor al fin de aportaciones).")

# Validación: fin aportes >= edad y objetivo >= fin aportes
if edad_fin_aportes < edad:
    st.error("La edad de fin de aportaciones no puede ser menor que la edad actual.")
if retiro < edad_fin_aportes:
    st.error("La edad objetivo debe ser mayor o igual al fin de aportaciones.")
# Validación simple de plazo
    plazo_anos = int(edad_fin_aportes - edad)
    if plazo_anos < 5:
        st.error("El plazo debe ser mayor a 5 años")

    ahorro_mensual = st.number_input("Ahorro Mensual", value=2000.0, step=500.0)
    
    st.subheader("Fiscalidad y Rendimiento")

    estrategia_fiscal = st.selectbox(
        "Estrategia Fiscal",
        ["Art 151 (PPR - Deducible)", "Art 93 (No Deducible)", "Art 185 (Diferimiento)"]
    )

    isr_cliente = st.selectbox(
        "% ISR del cliente",
        ["10%", "15%", "20%", "25%", "30%", "32%", "34%", "35%"],
        index=4
    )
    isr_cliente = float(isr_cliente.replace("%", "")) / 100.0

    sueldo_anual = 0.0
    validar_sueldo = False

    if estrategia_fiscal == "Art 151 (PPR - Deducible)":
        validar_sueldo = st.checkbox("¿Validar tope con Sueldo Anual?")
        if validar_sueldo:
            sueldo_anual = st.number_input("Sueldo Bruto Anual", value=600000.0, step=10000.0)
            st.caption(f"Tope 10% ingresos: {sueldo_anual*0.10:,.0f} MXN")
        else:
            st.caption(f"Se usará tope anual absoluto Art. 151: {TOPE_ART_151_ABS:,.0f} MXN (estimado).")

    reinvertir_beneficio = st.radio(
        "Beneficio fiscal",
        ["Retirar (cash)", "Reinvertir en el plan"],
        horizontal=True,
        index=0
    ) == "Reinvertir en el plan"

    perfil_k360 = st.selectbox(
        "Perfil de inversión (K360)",
        ["Conservador", "Balanceado (Recomendado)", "Dinámico (Optimista)"],
        index=1
    )

    tasas_perfil = {
        "Conservador": 0.06,
        "Balanceado (Recomendado)": 0.085,
        "Dinámico (Optimista)": 0.105
    }
    tasa_bruta_sugerida = tasas_perfil.get(perfil_k360, 0.085)

    modo_avanzado = st.checkbox("Modo avanzado: definir tasa manual", value=False)
    # Tasa bruta siempre editable (premium + fácil de actualizar año con año)
    tasa_bruta = st.slider(
        "Tasa Mercado Bruta (%)",
        0.0, 20.0,
        float(tasa_bruta_sugerida * 100),
        step=0.1
    ) / 100.0
    st.caption(f"Sugerencia por perfil ({perfil_k360}): {tasa_bruta_sugerida*100:.2f}% — puedes ajustarla según mercado/año.")

    # Inflación editable (default 5% para alinear con simuladores comerciales tipo Allianz)
    inflacion = st.checkbox("Considerar Incremento con Inflación", value=True)
    inflacion_pct = st.number_input(
        "Inflación anual (%)",
        min_value=0.0, max_value=15.0,
        value=5.0,
        step=0.1,
        help="Puedes actualizar este supuesto cada año (ej. 5.0%, 4.5%, 6.0%)."
    )
    tasa_inflacion = (inflacion_pct / 100.0) if inflacion else 0.0

    
    st.markdown("---")
    st.subheader("Personalización (PDF)")
    uploaded_logo = st.file_uploader("Cargar Logotipo (Opcional)", type=['png', 'jpg', 'jpeg'])
    asesor_nombre = st.text_input("Nombre del Asesor", value="Tu Nombre Aquí")
    asesor_telefono = st.text_input("Teléfono / WhatsApp", value="55-0000-0000")

# --- 2. CÁLCULOS MATEMÁTICOS ---

# --- APLICACIÓN DE TASA REAL (ALLIANZ) ---
tasa_admin_real = obtener_tasa_admin(ahorro_mensual, plazo_anos)
tasa_interes_neta = tasa_bruta - tasa_admin_real  # Restamos el costo administrativo a la tasa bruta

# Hardening: evita tasa neta negativa (puede ocurrir con aportaciones bajas / plazos cortos)
if tasa_interes_neta < 0:
    st.warning(
        f"⚠️ La tasa neta resultó negativa (bruta {tasa_bruta*100:.2f}% - admin {tasa_admin_real*100:.2f}%). "
        "Se ajustó a 0.00% para evitar proyecciones irreales."
    )
    tasa_interes_neta = 0.0


contrib_meses = int(plazo_anos) * 12
    total_meses = int((retiro - edad) * 12)
data = []

saldo = 0
aporte_actual = ahorro_mensual
total_aportado = 0
acumulado_devoluciones = 0

# Definir el tope deducible anual según la estrategia
tope_deducible_anual = 0

if estrategia_fiscal == "Art 151 (PPR - Deducible)":
    tope_deducible_anual = TOPE_ART_151_ABS
    if validar_sueldo:
        tope_deducible_anual = min(TOPE_ART_151_ABS, sueldo_anual * 0.10)
elif estrategia_fiscal == "Art 185 (Diferimiento)":
    tope_deducible_anual = TOPE_ART_185
else:
    tope_deducible_anual = 0 # Art 93 no deduce

# Bucle de Proyección
for i in range(1, meses + 1):
    # Rendimiento sobre saldo acumulado (usando Tasa Neta)
    rendimiento_mensual = saldo * (tasa_interes_neta / 12)
    aporte_mes = aporte_actual if i <= contrib_meses else 0.0
        saldo += rendimiento_mensual + aporte_mes
        if i == contrib_meses:
            saldo_al_fin_aportes = saldo
    total_aportado += aporte_actual
    
    # Ajuste inflacionario anual de la aportación
    if i % 12 == 0 and inflacion and i <= contrib_meses:
        aporte_actual *= (1 + tasa_inflacion)
    
    # Cálculo Beneficio Fiscal (SAT)
    # Lo calculamos año con año para que sea exacto y sumamos el monto nominal
    if estrategia_fiscal != "Art 93 (No Deducible)":
        if i % 12 == 0: # Al final de cada año calculamos la devolución de ese año
            aporte_anual_real = aporte_actual * 12 # Aprox del año corriente
            # La base de devolución es el menor entre lo aportado y el tope legal
            base_devolucion = min(aporte_anual_real, tope_deducible_anual)
            devolucion_anio = base_devolucion * isr_cliente
            acumulado_devoluciones += devolucion_anio
            if reinvertir_beneficio:
                saldo += devolucion_anio

    data.append({
        "Mes": i,
        "Año": edad + (i/12),
        "Saldo Neto": saldo,
        "Aportado": total_aportado,
        # Guardamos el acumulado para la gráfica
        "Devoluciones SAT": acumulado_devoluciones 
    })

df = pd.DataFrame(data)

# --- 3. LÓGICA DE ALERTAS Y TEXTOS ---
aportacion_primer_ano = ahorro_mensual * 12
excedente = 0
mostrar_alerta = False
texto_alerta_pdf = ""
texto_analisis_pdf = ""

# Lógica específica por artículo
if estrategia_fiscal == "Art 151 (PPR - Deducible)":
    texto_analisis_pdf = "Plan Deducible (Art. 151 LISR). Permite deducir aportaciones anuales dentro de los límites establecidos por la ley (10% de ingresos anuales hasta un tope absoluto). La deducción aplica en la declaración anual. Al momento del retiro, el monto acumulado puede considerarse ingreso acumulable; existen exenciones conforme a UMAs vigentes y el excedente podría pagar impuestos. Fecha objetivo para considerar deducibilidad del año: 31 de diciembre (según material del producto)."
    if aportacion_primer_ano > tope_deducible_anual:
        mostrar_alerta = True
        excedente = aportacion_primer_ano - tope_deducible_anual
        texto_alerta_pdf = (
            f"Tu aportación anual ({aportacion_primer_ano:,.2f} MXN) excede el tope deducible estimado "
            f"({tope_deducible_anual:,.2f} MXN). El excedente no es deducible."
        )

elif estrategia_fiscal == "Art 185 (Diferimiento)":
    texto_analisis_pdf = "Plan con Diferimiento (Art. 185 LISR). Permite deducir aportaciones hasta el tope anual indicado en el material del producto. Al retiro o disposición, podría aplicar la tasa de ISR correspondiente sobre el saldo según reglas vigentes (diferimiento fiscal). Fecha objetivo de referencia: 30 de abril (según material del producto)."
    if aportacion_primer_ano > TOPE_ART_185:
        mostrar_alerta = True
        excedente = aportacion_primer_ano - TOPE_ART_185
        texto_alerta_pdf = "Tu aportación anual excede el tope estimado del Artículo 185."

elif estrategia_fiscal == "Art 93 (No Deducible)":
    texto_analisis_pdf = "Plan No Deducible (Art. 93 LISR). No genera deducción durante la etapa de ahorro. Al cumplir con requisitos legales aplicables, el saldo podría recibirse de forma exenta."


# --- 4. INTERFAZ PRINCIPAL ---

st.title("🛡️ Simulador Krece360 - OptiMaxx")
st.markdown("Herramienta de proyección financiera.")

# Alerta Visual (Amarilla)
if mostrar_alerta:
    st.warning(f"""
    ⚠️ **¡Atención! Tu aportación excede el límite deducible.**
    
    {texto_alerta_pdf}
    
    * Se aprovecha el beneficio fiscal hasta el tope: **${tope_deducible_anual:,.2f}**
    """)

# Métricas
col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="Total Aportado", value=f"${total_aportado:,.0f}")
with col2:
    st.metric(label="Saldo Final (Neto)", value=f"${saldo:,.0f}", delta=f"Costo Admin: {tasa_admin_real*100:.2f}%")
with col3:
    # Mostramos el acumulado directo calculado en el bucle (CORRECCIÓN FINAL)
    st.metric(label="Beneficio SAT Total", value=f"${acumulado_devoluciones:,.0f}", delta="Dinero recuperado")

st.markdown("---")

# Gráfica
st.subheader("Proyección Real")
df_chart = df[["Año", "Saldo Neto", "Aportado", "Devoluciones SAT"]].melt('Año', var_name='Categoría', value_name='Monto')

chart = alt.Chart(df_chart).mark_line().encode(
    x='Año',
    y='Monto',
    color=alt.Color('Categoría', scale=alt.Scale(domain=['Aportado', 'Saldo Neto', 'Devoluciones SAT'], range=['#ff4b4b', '#1f77b4', '#2ca02c'])),
    tooltip=['Año', 'Categoría', alt.Tooltip('Monto', format='$,.0f')]
).properties(height=400)

st.altair_chart(chart, use_container_width=True)


# -----------------------------
# Comparador de escenarios (UI)
# -----------------------------
st.markdown("---")
st.subheader("📊 Comparación de Escenarios")
st.caption("Mismos datos, distintos supuestos. No es promesa: es simulación con diferentes niveles de riesgo.")

escenarios = [
    {"Escenario": "🟢 Conservador", "Perfil": "Conservador", "Moneda": "MXN", "tasa_bruta": 0.06},
    {"Escenario": "⭐ Recomendado K360", "Perfil": "Balanceado", "Moneda": "MXN", "tasa_bruta": 0.085},
    {"Escenario": "🟠 Optimista (Allianz-style)", "Perfil": "Dinámico", "Moneda": "USD", "tasa_bruta": 0.105},
]

if modo_avanzado:
    escenarios.insert(2, {"Escenario": "🟣 Personalizado (tu tasa)", "Perfil": "Manual", "Moneda": "—", "tasa_bruta": float(tasa_bruta)})

comparador_pdf = []
rows = []
for s in escenarios:
    saldo_final_s, tasa_neta_s = proyectar_saldo_final(
        ahorro_mensual=float(ahorro_mensual),
        plazo_anos=int(plazo_anos),
        edad=int(edad),
        tasa_bruta_scenario=float(s["tasa_bruta"]),
        tasa_admin_real=float(tasa_admin_real),
        inflacion=bool(inflacion),
        tasa_inflacion=float(tasa_inflacion),
        estrategia_fiscal=str(estrategia_fiscal),
        validar_sueldo=bool(validar_sueldo),
        sueldo_anual=float(sueldo_anual),
        isr_cliente=float(isr_cliente),
        tope_art_151_abs=float(TOPE_ART_151_ABS),
        tope_art_185=float(TOPE_ART_185),
        reinvertir_beneficio=bool(reinvertir_beneficio),
    )
    # Calibración Allianz (solo para el escenario Allianz-style)
    if 'Allianz-style' in str(s.get('Escenario','')):
        saldo_final_s = float(saldo_final_s) * float(FACTOR_CALIBRACION_ALLIANZ)

    comparador_pdf.append({
        'escenario': str(s['Escenario']),
        'tasa_neta_pct': float(tasa_neta_s)*100.0,
        'monto_retiro': float(saldo_final_s),
    })

    rows.append({
        "Escenario": s["Escenario"],
        "Perfil": s["Perfil"],
        "Moneda": s["Moneda"],
        "Tasa Bruta": f"{float(s['tasa_bruta'])*100:.2f}%",
        "Tasa Neta (bruta - admin)": f"{float(tasa_neta_s)*100:.2f}%",
        "Monto estimado al retiro": f"${float(saldo_final_s):,.0f}",
    })

df_comp = pd.DataFrame(rows)
st.dataframe(df_comp, hide_index=True, use_container_width=True)

st.info(
    "ℹ️ **Por qué cambia el monto:** el rendimiento depende del nivel de riesgo (perfil) y los supuestos. "
    "El escenario optimista puede tener años negativos; el conservador prioriza estabilidad."
)


st.info(f"""
ℹ️ **Cálculo de Costos:** Se está aplicando una tasa administrativa de **{tasa_admin_real*100:.2f}%** anual, 
correspondiente a una aportación de ${ahorro_mensual:,.0f} a un plazo de {plazo_anos} años (Según Tabla Allianz).
""")

# --- 5. SECCIÓN DE DESCARGA PDF ---
st.markdown("### 📄 Exportar Propuesta")

if st.button("Generar PDF"):
    logo_path_temp = None
    try:
        logo_path_temp = _save_logo_to_temp(uploaded_logo)
    except Exception as e:
        st.error(f"⚠️ No se pudo cargar el logotipo: {e}")
        logo_path_temp = None
    # Generar PDF
    # CORRECCIÓN: Pasamos 'acumulado_devoluciones' DIRECTO, sin multiplicar por años otra vez.
    try:
        pdf_bytes, error = crear_pdf(
            {'nombre': nombre, 'edad': edad, 'retiro': retiro, 'estrategia': estrategia_fiscal},
            {
                'aporte_mensual': ahorro_mensual,
                'saldo_final': saldo,
                'beneficio_sat': acumulado_devoluciones,
                'tasa_admin_pct': tasa_admin_real * 100,
                'total_aportado': total_aportado,
                'comparador': comparador_pdf
            },
            {'texto_analisis': texto_analisis_pdf, 'alerta_excedente': texto_alerta_pdf},
            {'nombre': asesor_nombre, 'telefono': asesor_telefono},
            logo_path_temp
        )
    finally:
        # Limpieza del archivo temporal del logo (si existe)
        if logo_path_temp and os.path.exists(logo_path_temp):
            try:
                os.remove(logo_path_temp)
            except Exception:
                pass
    
    if error:
        st.error(f"Error al generar PDF: {error}")
    else:
        st.success("✅ PDF Generado con éxito")
        st.download_button(
            label="⬇️ Descargar PDF",
            data=pdf_bytes,
            file_name=f"Propuesta_Krece360_{_safe_filename(nombre)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf"
        )

# MANUAL_AGENTES_K360
# - Optimista (Allianz-style): escenario calibrado para comparar con simuladores comerciales.
# - Recomendado K360: equilibrio entre crecimiento y riesgo (sugerido).
# - Personalizado: planeación avanzada con tasa editable.
