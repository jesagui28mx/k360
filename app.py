import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from fpdf import FPDF
import base64
from datetime import datetime
import os

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Cotizador OptiMaxx Plus", layout="wide", page_icon="🛡️")

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
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- LÓGICA DE NEGOCIO ALLIANZ (MATRIZ DE COSTOS) ---
def obtener_tasa_admin(aporte_mensual, plazo_anios):
    """
    Fuente: PDF OptiMaxx Plus, Página 9.
    Devuelve la tasa de cargo administrativo según Aportación y Plazo.
    """
    # 1. Determinar columna (Plazo)
    if plazo_anios >= 25:
        col_idx = 2 # Columna 25 años
    elif plazo_anios >= 20:
        col_idx = 1 # Columna 20 años
    else:
        col_idx = 0 # Columna 15 años (Default para menores también)

    # 2. Determinar fila (Monto) - Tabla Oficial
    # Formato: (Monto Mínimo, [Tasa 15, Tasa 20, Tasa 25])
    tabla_costos = [
        (10000, [0.0183, 0.0162, 0.0153]), # Más de 10k
        (7500,  [0.0187, 0.0165, 0.0156]), 
        (5000,  [0.0197, 0.0175, 0.0164]), 
        (4000,  [0.0206, 0.0181, 0.0169]), 
        (2500,  [0.0228, 0.0199, 0.0184]), # Base estándar
        (0,     [0.0228, 0.0199, 0.0184])  # Menos de 2,500 (Aplica tasa base)
    ]

    tasa_admin = 0.0228 # Valor por defecto (el más alto) por seguridad
    
    for monto_min, tasas in tabla_costos:
        if aporte_mensual >= monto_min:
            tasa_admin = tasas[col_idx]
            break
            
    return tasa_admin

# --- CLASE PDF ---
class PDFReport(FPDF):
    def __init__(self, logo_path=None):
        super().__init__()
        self.logo_path = logo_path
        self.fecha_actual = datetime.now().strftime("%d/%m/%Y")

    def header(self):
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                self.image(self.logo_path, 10, 8, 33) 
            except Exception:
                pass 
        
        self.set_font('Arial', 'B', 15)
        self.cell(40)
        self.cell(0, 10, 'Allianz OptiMaxx Plus - Proyección', 0, 0, 'L')
        
        self.set_font('Arial', 'I', 10)
        self.cell(0, 10, f'Fecha: {self.fecha_actual}', 0, 1, 'R')
        self.ln(5)

    def footer(self):
        self.set_y(-35)
        self.set_font('Arial', '', 7)
        self.set_text_color(100, 100, 100)
        
        disclaimer = (
            "AVISO LEGAL: Este documento es una ilustración basada en los parámetros del producto OptiMaxx Plus. "
            "Los rendimientos pasados no garantizan rendimientos futuros. La tasa administrativa aplicada corresponde "
            "a la matriz de cargos vigente (Pág 9 Condiciones Generales). El tratamiento fiscal es responsabilidad del contratante "
            "y está sujeto a la Ley del ISR vigente. No constituye una oferta vinculante."
        )
        self.multi_cell(0, 3, disclaimer, 0, 'C')

        self.set_y(-15)
        self.set_text_color(0, 0, 0)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()} | Generado con Cotizador Pro', 0, 0, 'C')

def crear_pdf(datos_cliente, datos_fin, datos_fiscales, datos_asesor, ruta_logo_temp):
    try:
        pdf = PDFReport(logo_path=ruta_logo_temp)
        pdf.add_page()
        pdf.ln(15) # Mantiene el espacio para no encimar el logo
        
        pdf.set_font("Arial", size=12)
        
        # Datos Cliente
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, f"Propuesta para: {datos_cliente['nombre']}", 0, 1)
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, f"Edad: {datos_cliente['edad']} | Plazo Plan: {datos_cliente['plazo']} años", 0, 1)
        pdf.cell(0, 10, f"Estrategia Fiscal: {datos_cliente['estrategia']}", 0, 1)
        pdf.ln(5)
        
        # Resumen Financiero
        pdf.set_fill_color(240, 242, 246)
        y_actual = pdf.get_y()
        pdf.rect(10, y_actual, 190, 45, 'F')
        pdf.set_y(y_actual + 5)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"   Aportación Mensual: ${datos_fin['aporte_mensual']:,.2f}", 0, 1)
        pdf.cell(0, 10, f"   Saldo Proyectado al Retiro: ${datos_fin['saldo_final']:,.2f}", 0, 1)
        pdf.cell(0, 10, f"   Beneficio SAT Total (Estimado): ${datos_fin['beneficio_sat']:,.2f}", 0, 1)
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 10, f"   (Costo Admin Aplicado según Matriz: {datos_fin['tasa_admin_pct']:.2f}% anual)", 0, 1)
        
        pdf.set_y(y_actual + 50)
        
        # Análisis Fiscal
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "Tratamiento Fiscal Seleccionado:", 0, 1)
        pdf.set_font("Arial", size=11)
        pdf.multi_cell(0, 8, datos_fiscales['texto_analisis'])
        
        # Alerta en ROJO si existe excedente
        if datos_fiscales['alerta_excedente']:
            pdf.ln(5)
            pdf.set_text_color(200, 0, 0)
            pdf.set_font("Arial", 'B', 10)
            pdf.multi_cell(0, 8, f"ATENCIÓN: {datos_fiscales['alerta_excedente']}")
            pdf.set_text_color(0, 0, 0)
            
        # Firma
        pdf.ln(20)
        pdf.set_draw_color(150, 150, 150)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y()) 
        pdf.ln(5)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "Asesor Financiero:", 0, 1)
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 8, f"{datos_asesor['nombre']}", 0, 1)
        pdf.cell(0, 8, f"Contacto: {datos_asesor['telefono']}", 0, 1)

        return pdf.output(dest='S').encode('latin-1', 'replace'), None
    except Exception as e:
        return None, str(e)

# --- SIDEBAR (CONFIGURACIÓN) ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/Allianz_SE.svg/2560px-Allianz_SE.svg.png", width=150)
    st.header("⚙️ Configuración")
    
    st.subheader("Cliente")
    nombre = st.text_input("Nombre", value="Cliente Allianz")
    edad = st.number_input("Edad Actual", 30, 60, 30)
    retiro = st.number_input("Edad de Retiro", 50, 75, 65)
    
    plazo_anos = retiro - edad
    if plazo_anos < 5:
        st.error("El plazo mínimo recomendado es de 5 años.")
    
    st.subheader("Inversión")
    ahorro_mensual = st.number_input("Aportación Mensual ($)", value=3000, step=500, min_value=1500)
    
    st.subheader("Estrategia Fiscal")
    estrategia_fiscal = st.selectbox("Selecciona Artículo LISR:", 
        ["Art 93 (No Deducible / Exento)", 
         "Art 151 (PPR - Deducible)", 
         "Art 185 (Diferimiento)"])
    
    # Validaciones Art 151
    sueldo_anual = 0
    validar_sueldo = False
    
    if estrategia_fiscal == "Art 151 (PPR - Deducible)":
        validar_sueldo = st.checkbox("Validar tope vs Ingreso Anual", value=True)
        if validar_sueldo:
            sueldo_anual = st.number_input("Ingreso Bruto Anual", value=600000, step=10000)
            st.caption(f"Tope 10%: ${sueldo_anual*0.10:,.0f}")

    st.markdown("---")
    tasa_bruta = st.slider("Tasa Bruta Fondo (%)", 8.0, 14.0, 10.0, help="S&P500 Promedio Histórico") / 100
    inflacion = st.checkbox("Indexar a Inflación (4%)", value=True)
    tasa_inflacion = 0.04 if inflacion else 0.0

    st.markdown("---")
    st.subheader("Personalización PDF")
    uploaded_logo = st.file_uploader("Logo Asesor", type=['png', 'jpg'])
    asesor_nombre = st.text_input("Tu Nombre", value="Asesor Certificado")
    asesor_telefono = st.text_input("Tu Celular", value="55-0000-0000")

# --- CÁLCULOS CENTRALES ---
UMA_ANUAL = 39606.36
TOPE_ART_151 = UMA_ANUAL * 5  # Aprox 198k
TOPE_ART_185 = 152000         # Tope fijo
ISR_ESTIMADO = 0.30

# 1. Obtener Costo Admin de la Matriz Oficial
tasa_admin_anual = obtener_tasa_admin(ahorro_mensual, plazo_anos)
tasa_neta = tasa_bruta - tasa_admin_anual

meses = plazo_anos * 12
data = []
saldo = 0
aporte_actual = ahorro_mensual
total_aportado = 0

# 2. Lógica de Topes y Alertas (RESTAURADA)
tope_deducible_anual = 0
mostrar_alerta = False
mensaje_alerta = ""
aporte_primer_ano = ahorro_mensual * 12

if estrategia_fiscal == "Art 151 (PPR - Deducible)":
    tope_legal = TOPE_ART_151
    if validar_sueldo:
        tope_legal = min(TOPE_ART_151, sueldo_anual * 0.10)
    
    tope_deducible_anual = tope_legal
    
    if aporte_primer_ano > tope_deducible_anual:
        mostrar_alerta = True
        excedente = aporte_primer_ano - tope_deducible_anual
        mensaje_alerta = f"Tu aportación anual (${aporte_primer_ano:,.0f}) supera el tope deducible (${tope_deducible_anual:,.0f}). El excedente (${excedente:,.0f}) se invierte pero NO deduce impuestos."

elif estrategia_fiscal == "Art 185 (Diferimiento)":
    tope_deducible_anual = TOPE_ART_185
    if aporte_primer_ano > TOPE_ART_185:
        mostrar_alerta = True
        mensaje_alerta = f"Superas el tope fijo de $152,000 anuales del Art 185."

# 3. Proyección Financiera
for i in range(1, meses + 1):
    rendimiento = saldo * (tasa_neta / 12)
    saldo += rendimiento + aporte_actual
    total_aportado += aporte_actual
    
    if i % 12 == 0 and inflacion:
        aporte_actual *= (1 + tasa_inflacion)
    
    data.append({
        "Mes": i,
        "Año": edad + (i/12),
        "Saldo Neto": saldo,
        "Aportado": total_aportado
    })

df = pd.DataFrame(data)

# 4. Beneficio SAT (Cálculo Conservador para evitar críticas)
beneficio_sat_total = 0
if estrategia_fiscal != "Art 93 (No Deducible / Exento)":
    # Usamos el tope para el cálculo
    base_calculo = min(aporte_primer_ano, tope_deducible_anual)
    # Proyección lineal simple: (Base * 30%) * Años
    # Esto es "a prueba de balas" porque es el dinero nominal que recibe
    beneficio_sat_total = (base_calculo * ISR_ESTIMADO) * plazo_anos

# --- INTERFAZ USUARIO ---
st.title("🛡️ Simulador Financiero OptiMaxx")
st.markdown(f"**Cliente:** {nombre} | **Plazo:** {plazo_anos} años | **Estrategia:** {estrategia_fiscal}")

# --- ALERTA VISUAL (RESTAURADA) ---
if mostrar_alerta:
    st.warning(f"⚠️ **ATENCIÓN: Límite Fiscal Excedido**\n\n{mensaje_alerta}")

# Métricas
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Aportado", f"${total_aportado:,.0f}")
with col2:
    st.metric("Saldo Final Proyectado", f"${saldo:,.0f}", delta=f"Costo Admin: {tasa_admin_anual*100:.2f}%")
with col3:
    st.metric("Beneficio SAT (Estimado)", f"${beneficio_sat_total:,.0f}", help="Suma nominal de devoluciones (Sin reinversión)")
with col4:
    ganancia = saldo - total_aportado
    st.metric("Ganancia Neta", f"${ganancia:,.0f}")

st.caption(f"ℹ️ **Nota Técnica:** Se aplica Tasa Administrativa de **{tasa_admin_anual*100:.2f}%** conforme a la tabla de cargos de Allianz (Monto ${ahorro_mensual:,.0f} vs Plazo {plazo_anos} años).")

# Gráfica
st.subheader("Proyección Patrimonial")
df_chart = df[["Año", "Saldo Neto", "Aportado"]].melt('Año', var_name='Concepto', value_name='Monto')
chart = alt.Chart(df_chart).mark_line().encode(
    x='Año',
    y='Monto',
    color=alt.Color('Concepto', scale=alt.Scale(domain=['Aportado', 'Saldo Neto'], range=['#909090', '#000080'])),
    tooltip=['Año', 'Concepto', alt.Tooltip('Monto', format='$,.0f')]
).properties(height=400)
st.altair_chart(chart, use_container_width=True)

# Generación PDF
st.markdown("### 📄 Entregable")
if st.button("Generar PDF Propuesta"):
    logo_path_temp = None
    if uploaded_logo is not None:
        with open("temp_logo.png", "wb") as f:
            f.write(uploaded_logo.getbuffer())
        logo_path_temp = "temp_logo.png"
    
    # Textos Dinámicos
    texto_analisis = ""
    if estrategia_fiscal == "Art 93 (No Deducible / Exento)":
        texto_analisis = "PLAN ARTÍCULO 93 LISR: Tus aportaciones NO son deducibles hoy. BENEFICIO: Al cumplir requisitos (60 años de edad + 5 de vigencia), el rendimiento real es EXENTO de impuestos (Tope ~3.7 MDP). Ideal para liquidez futura libre de impuestos."
    elif estrategia_fiscal == "Art 151 (PPR - Deducible)":
        texto_analisis = "PLAN PPR (ART 151 LISR): Tus aportaciones son DEDUCIBLES en la declaración anual (Tope 10% ingresos o 5 UMAs). Generas saldo a favor hoy. Al retiro (65 años), el monto es acumulable con exención de 90 UMAs."
    elif estrategia_fiscal == "Art 185 (Diferimiento)":
        texto_analisis = "PLAN ARTÍCULO 185 LISR: Deducible hasta $152,000 pesos anuales. Este beneficio es un DIFERIMIENTO: deduces hoy, pero al momento del retiro se retiene el impuesto sobre el 100% del monto."

    pdf_bytes, error = crear_pdf(
        {'nombre': nombre, 'edad': edad, 'retiro': retiro, 'plazo': plazo_anos, 'estrategia': estrategia_fiscal},
        {'aporte_mensual': ahorro_mensual, 'saldo_final': saldo, 'beneficio_sat': beneficio_sat_total, 'tasa_admin_pct': tasa_admin_anual*100},
        {'texto_analisis': texto_analisis, 'alerta_excedente': mensaje_alerta if mostrar_alerta else ""},
        {'nombre': asesor_nombre, 'telefono': asesor_telefono},
        logo_path_temp
    )
    
    if error:
        st.error(f"Error: {error}")
    else:
        st.success("PDF Generado correctamente.")
        st.download_button("⬇️ Descargar PDF", data=pdf_bytes, file_name=f"Propuesta_OptiMaxx_{nombre}.pdf", mime="application/pdf")
