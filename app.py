import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from fpdf import FPDF
import base64
from datetime import datetime
import os

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Simulador Krece360", layout="wide", page_icon="🛡️")

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

# --- CLASE PDF MODIFICADA (HEADER/FOOTER) ---
class PDFReport(FPDF):
    def __init__(self, logo_path=None):
        super().__init__()
        self.logo_path = logo_path
        self.fecha_actual = datetime.now().strftime("%d/%m/%Y")

    def header(self):
        # 1. Logotipo
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                self.image(self.logo_path, 10, 8, 33) 
            except Exception:
                pass 
        
        # 2. Título
        self.set_font('Arial', 'B', 15)
        self.cell(40)
        self.cell(0, 10, 'Krece360 - Proyección Financiera', 0, 0, 'L')
        
        # 3. Fecha
        self.set_font('Arial', 'I', 10)
        self.cell(0, 10, f'Fecha: {self.fecha_actual}', 0, 1, 'R')
        self.ln(5)

    def footer(self):
        # --- NUEVO DISCLAIMER (Petición Usuario) ---
        self.set_y(-32)
        self.set_font('Arial', '', 7)
        self.set_text_color(100, 100, 100)
        
        disclaimer = (
            "AVISO LEGAL: Esta proyección es de carácter exclusivamente informativo y representa una simulación basada en los datos proporcionados. "
            "No constituye una oferta formal, contrato vinculante ni garantía de rendimientos futuros. La tasa administrativa aplicada corresponde "
            "a la matriz oficial del producto. Para una cotización formal, contacte a su asesor."
        )
        self.multi_cell(0, 3, disclaimer, 0, 'C')
        
        # Paginación
        self.set_y(-15)
        self.set_text_color(0, 0, 0)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()} | Generado con Simulador Krece360', 0, 0, 'C')

def crear_pdf(datos_cliente, datos_fin, datos_fiscales, datos_asesor, ruta_logo_temp):
    try:
        pdf = PDFReport(logo_path=ruta_logo_temp)
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
        
        # Resumen Financiero
        pdf.set_fill_color(240, 242, 246)
        y_actual = pdf.get_y()
        pdf.rect(10, y_actual, 190, 45, 'F') # Ajusté un poco la altura
        
        pdf.set_y(y_actual + 5)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"   Aportación Mensual: ${datos_fin['aporte_mensual']:,.2f}", 0, 1)
        pdf.cell(0, 10, f"   Saldo Estimado al Retiro: ${datos_fin['saldo_final']:,.2f}", 0, 1)
        pdf.cell(0, 10, f"   Beneficio SAT Estimado: ${datos_fin['beneficio_sat']:,.2f}", 0, 1) # Aquí va el dato corregido
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 10, f"   (Tasa Admin Aplicada: {datos_fin['tasa_admin_pct']:.2f}%)", 0, 1)
        
        pdf.set_y(y_actual + 50)
        
        # Análisis Fiscal
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "Análisis Fiscal:", 0, 1)
        pdf.set_font("Arial", size=11)
        pdf.multi_cell(0, 8, datos_fiscales['texto_analisis'])
        
        if datos_fiscales['alerta_excedente']:
            pdf.ln(5)
            pdf.set_text_color(200, 0, 0)
            pdf.multi_cell(0, 8, f"NOTA IMPORTANTE: {datos_fiscales['alerta_excedente']}")
            pdf.set_text_color(0, 0, 0)
            
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

        return pdf.output(dest='S').encode('latin-1', 'replace'), None
    except Exception as e:
        return None, str(e)

# --- 1. SIDEBAR ---
with st.sidebar:
    st.image("https://via.placeholder.com/150x50?text=Logo+Krece360", use_column_width=True) 
    st.header("⚙️ Parámetros")
    
    st.subheader("Datos del Prospecto")
    nombre = st.text_input("Nombre Cliente", value="Juan Pérez")
    
    st.subheader("Configuración Plan")
    col_edad, col_retiro = st.columns(2)
    edad = col_edad.number_input("Edad", value=30, step=1)
    retiro = col_retiro.number_input("Edad Retiro", value=65, step=1)
    
    # Validación simple de plazo
    plazo_anos = retiro - edad
    if plazo_anos < 5:
        st.error("El plazo debe ser mayor a 5 años")

    ahorro_mensual = st.number_input("Ahorro Mensual", value=2000.0, step=500.0)
    
    st.subheader("Fiscalidad y Rendimiento")
    # Agregamos la opción Art 185 que pediste
    estrategia_fiscal = st.selectbox("Estrategia Fiscal", 
                                     ["Art 151 (PPR - Deducible)", 
                                      "Art 93 (No Deducible)", 
                                      "Art 185 (Diferimiento)"])
    
    sueldo_anual = 0
    validar_sueldo = False
    
    if estrategia_fiscal == "Art 151 (PPR - Deducible)":
        validar_sueldo = st.checkbox("¿Validar tope con Sueldo Anual?")
        if validar_sueldo:
            sueldo_anual = st.number_input("Sueldo Bruto Anual", value=600000.0, step=10000.0)
            st.caption(f"Tope 10% ingresos: ${sueldo_anual*0.10:,.0f}")
        else:
            st.caption("Se usará tope estándar de 5 UMAs.")

    tasa_bruta = st.slider("Tasa Mercado Bruta (%)", 5.0, 15.0, 10.0) / 100
    inflacion = st.checkbox("Considerar Inflación (4%)", value=True)
    tasa_inflacion = 0.04 if inflacion else 0.0
    
    st.markdown("---")
    st.subheader("Personalización (PDF)")
    uploaded_logo = st.file_uploader("Cargar Logotipo (Opcional)", type=['png', 'jpg', 'jpeg'])
    asesor_nombre = st.text_input("Nombre del Asesor", value="Tu Nombre Aquí")
    asesor_telefono = st.text_input("Teléfono / WhatsApp", value="55-0000-0000")

# --- 2. CÁLCULOS MATEMÁTICOS ---

UMA_ANUAL = 39606.36
TOPE_5_UMAS = UMA_ANUAL * 5 
TOPE_ART_185 = 152000.0 # Dato fijo de Ley
ISR_ESTIMADO = 0.30 

# --- APLICACIÓN DE TASA REAL (ALLIANZ) ---
tasa_admin_real = obtener_tasa_admin(ahorro_mensual, plazo_anos)
tasa_interes_neta = tasa_bruta - tasa_admin_real # Restamos el costo administrativo a la tasa bruta

meses = plazo_anos * 12
data = []

saldo = 0
aporte_actual = ahorro_mensual
total_aportado = 0
acumulado_devoluciones = 0

# Definir el tope deducible anual según la estrategia
tope_deducible_anual = 0

if estrategia_fiscal == "Art 151 (PPR - Deducible)":
    tope_deducible_anual = TOPE_5_UMAS
    if validar_sueldo:
        tope_deducible_anual = min(TOPE_5_UMAS, sueldo_anual * 0.10)
elif estrategia_fiscal == "Art 185 (Diferimiento)":
    tope_deducible_anual = TOPE_ART_185
else:
    tope_deducible_anual = 0 # Art 93 no deduce

# Bucle de Proyección
for i in range(1, meses + 1):
    # Rendimiento sobre saldo acumulado (usando Tasa Neta)
    rendimiento_mensual = saldo * (tasa_interes_neta / 12)
    saldo += rendimiento_mensual + aporte_actual
    total_aportado += aporte_actual
    
    # Ajuste inflacionario anual de la aportación
    if i % 12 == 0 and inflacion:
        aporte_actual *= (1 + tasa_inflacion)
    
    # Cálculo Beneficio Fiscal (SAT)
    # Lo calculamos año con año para que sea exacto y sumamos el monto nominal
    if estrategia_fiscal != "Art 93 (No Deducible)":
        if i % 12 == 0: # Al final de cada año calculamos la devolución de ese año
            aporte_anual_real = aporte_actual * 12 # Aprox del año corriente
            # La base de devolución es el menor entre lo aportado y el tope legal
            base_devolucion = min(aporte_anual_real, tope_deducible_anual)
            devolucion_anio = base_devolucion * ISR_ESTIMADO
            acumulado_devoluciones += devolucion_anio

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
    texto_analisis_pdf = "Plan Deducible (Art 151 LISR). Genera devoluciones hoy, sujeto a retención al retiro sobre el excedente de 90 UMAs."
    if aportacion_primer_ano > tope_deducible_anual:
        mostrar_alerta = True
        excedente = aportacion_primer_ano - tope_deducible_anual
        texto_alerta_pdf = f"Tu aportación anual (${aportacion_primer_ano:,.2f}) excede el tope deducible (${tope_deducible_anual:,.2f}). El excedente no es deducible."

elif estrategia_fiscal == "Art 185 (Diferimiento)":
    texto_analisis_pdf = "Plan Art 185 LISR. Deducible hasta $152,000. Al retiro se retiene el ISR correspondiente al 100% del saldo (Diferimiento fiscal)."
    if aportacion_primer_ano > TOPE_ART_185:
        mostrar_alerta = True
        excedente = aportacion_primer_ano - TOPE_ART_185
        texto_alerta_pdf = f"Tu aportación supera el tope fijo de $152,000 del Art 185."

elif estrategia_fiscal == "Art 93 (No Deducible)":
    texto_analisis_pdf = "Plan Exento (Art 93 LISR). No deducible hoy. Al cumplir requisitos (60 años + 5 vigencia), el rendimiento es EXENTO de impuestos."


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

st.info(f"""
ℹ️ **Cálculo de Costos:** Se está aplicando una tasa administrativa de **{tasa_admin_real*100:.2f}%** anual, 
correspondiente a una aportación de ${ahorro_mensual:,.0f} a un plazo de {plazo_anos} años (Según Tabla Allianz).
""")

# --- 5. SECCIÓN DE DESCARGA PDF ---
st.markdown("### 📄 Exportar Propuesta")

if st.button("Generar PDF"):
    logo_path_temp = None
    if uploaded_logo is not None:
        with open("temp_logo_upload.png", "wb") as f:
            f.write(uploaded_logo.getbuffer())
        logo_path_temp = "temp_logo_upload.png"
    
    # Generar PDF
    # CORRECCIÓN: Pasamos 'acumulado_devoluciones' DIRECTO, sin multiplicar por años otra vez.
    pdf_bytes, error = crear_pdf(
        {'nombre': nombre, 'edad': edad, 'retiro': retiro, 'estrategia': estrategia_fiscal},
        {
            'aporte_mensual': ahorro_mensual, 
            'saldo_final': saldo, 
            'beneficio_sat': acumulado_devoluciones, # <--- DATO CORREGIDO
            'tasa_admin_pct': tasa_admin_real * 100
        },
        {'texto_analisis': texto_analisis_pdf, 'alerta_excedente': texto_alerta_pdf},
        {'nombre': asesor_nombre, 'telefono': asesor_telefono},
        logo_path_temp 
    )
    
    if error:
        st.error(f"Error al generar PDF: {error}")
    else:
        st.success("✅ PDF Generado con éxito")
        st.download_button(
            label="⬇️ Descargar PDF",
            data=pdf_bytes,
            file_name=f"Propuesta_Krece360_{nombre}.pdf",
            mime="application/pdf"
        )
