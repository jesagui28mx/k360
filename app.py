import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from fpdf import FPDF
import base64
from datetime import datetime
import os

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Simulador PPR", layout="wide", page_icon="🛡️")

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

# --- CLASE PDF (LOGOTIPO DINÁMICO, FECHA Y DISCLAIMER) ---
class PDFReport(FPDF):
    def __init__(self, logo_path=None):
        super().__init__()
        self.logo_path = logo_path
        self.fecha_actual = datetime.now().strftime("%d/%m/%Y")

    def header(self):
        # 1. Logotipo (si existe)
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                self.image(self.logo_path, 10, 8, 33) 
            except Exception:
                pass 
        
        # 2. Título
        self.set_font('Arial', 'B', 15)
        self.cell(40) # Espacio para el logo
        self.cell(0, 10, 'PPR - Proyección Financiera', 0, 0, 'L')
        
        # 3. Fecha (Esquina derecha)
        self.set_font('Arial', 'I', 10)
        self.cell(0, 10, f'Fecha: {self.fecha_actual}', 0, 1, 'R')
        
        # Salto inicial del header
        self.ln(5)

    def footer(self):
        # --- AVISO LEGAL (DISCLAIMER) ---
        self.set_y(-32) # Subimos la posición para que quepa el texto legal
        self.set_font('Arial', '', 7)
        self.set_text_color(100, 100, 100) # Color gris para no distraer
        
        disclaimer = (
            "AVISO LEGAL: Los rendimientos y montos en este documento son estimativos, de carácter exclusivamente " 
            "informativos y no constituye una cotización formal "
            "ni una oferta vinculante por parte de una compañía de seguros. "
            "Para obtener una cotización oficial y proceder a la contratación, por favor comuníquese con su asesor."
        )
        self.multi_cell(0, 3, disclaimer, 0, 'C') # Centrado y con salto de línea automático

        # --- PAGINACIÓN ---
        self.set_y(-15)
        self.set_text_color(0, 0, 0) # Volvemos a color negro
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()} | Generado con Simulador Krece360', 0, 0, 'C')

def crear_pdf(datos_cliente, datos_fin, datos_fiscales, datos_asesor, ruta_logo_temp):
    try:
        # Pasamos la ruta del logo al constructor
        pdf = PDFReport(logo_path=ruta_logo_temp)
        pdf.add_page()
        
        # --- CORRECCIÓN DE ESPACIO PARA LOGO ---
        pdf.ln(15) # Espacio vertical extra para que el texto no choque con el logo
        
        pdf.set_font("Arial", size=12)
        
        # Título y Datos Cliente
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, f"Propuesta para: {datos_cliente['nombre']}", 0, 1)
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, f"Edad Actual: {datos_cliente['edad']} | Edad Retiro: {datos_cliente['retiro']}", 0, 1)
        pdf.cell(0, 10, f"Estrategia: {datos_cliente['estrategia']}", 0, 1)
        pdf.ln(5)
        
        # Resumen Financiero
        pdf.set_fill_color(240, 242, 246)
        
        # Guardamos posición Y para dibujar rectángulo
        y_actual = pdf.get_y()
        pdf.rect(10, y_actual, 190, 40, 'F')
        
        # Movemos el cursor dentro del cuadro
        pdf.set_y(y_actual + 5)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"   Aportación Mensual: ${datos_fin['aporte_mensual']:,.2f}", 0, 1)
        pdf.cell(0, 10, f"   Saldo Estimado al Retiro: ${datos_fin['saldo_final']:,.2f}", 0, 1)
        pdf.cell(0, 10, f"   Beneficio SAT Estimado: ${datos_fin['beneficio_sat']:,.2f}", 0, 1)
        
        # Salimos del área del rectángulo
        pdf.set_y(y_actual + 45)
        
        # Nota Fiscal
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "Análisis Fiscal:", 0, 1)
        pdf.set_font("Arial", size=11)
        pdf.multi_cell(0, 8, datos_fiscales['texto_analisis'])
        
        if datos_fiscales['alerta_excedente']:
            pdf.ln(5)
            pdf.set_text_color(200, 0, 0)
            pdf.multi_cell(0, 8, f"NOTA: {datos_fiscales['alerta_excedente']}")
            pdf.set_text_color(0, 0, 0)
            
        # Firma del Asesor
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

# --- 1. SIDEBAR (DATOS DEL PROSPECTO Y CONFIGURACIÓN) ---
with st.sidebar:
    st.image("https://via.placeholder.com/150x50?text=Logo+Krece360", use_column_width=True) 
    st.header("⚙️ Parámetros")
    
    st.subheader("Datos del Prospecto")
    nombre = st.text_input("Nombre Cliente", value="Juan Pérez")
    
    st.subheader("Configuración Plan")
    col_edad, col_retiro = st.columns(2)
    edad = col_edad.number_input("Edad", value=30, step=1)
    retiro = col_retiro.number_input("Edad Retiro", value=65, step=1)
    
    ahorro_mensual = st.number_input("Ahorro Mensual", value=2000, step=500)
    
    st.subheader("Fiscalidad y Rendimiento")
    estrategia_fiscal = st.selectbox("Estrategia Fiscal", ["Art 151 (PPR - Deducible)", "Art 93 (No Deducible)"])
    
    sueldo_anual = 0
    validar_sueldo = False
    
    if estrategia_fiscal == "Art 151 (PPR - Deducible)":
        validar_sueldo = st.checkbox("¿Validar tope con Sueldo Anual?")
        if validar_sueldo:
            sueldo_anual = st.number_input("Sueldo Bruto Anual", value=600000, step=10000)
            st.caption(f"Tope 10% ingresos: ${sueldo_anual*0.10:,.0f}")
        else:
            st.caption("Se usará tope estándar de 5 UMAs.")

    tasa_interes = st.slider("Tasa Mercado Bruta (%)", 5.0, 15.0, 10.0) / 100
    inflacion = st.checkbox("Considerar Inflación (4%)", value=True)
    tasa_inflacion = 0.04 if inflacion else 0.0
    
    # --- NUEVA SECCIÓN: PERSONALIZACIÓN (LOGO Y DATOS) ---
    st.markdown("---")
    st.subheader("Personalización (PDF)")
    
    # Subida de Logo
    uploaded_logo = st.file_uploader("Cargar Logotipo (Opcional)", type=['png', 'jpg', 'jpeg'])
    
    asesor_nombre = st.text_input("Nombre del Asesor", value="Tu Nombre Aquí")
    asesor_telefono = st.text_input("Teléfono / WhatsApp", value="55-0000-0000")

# --- 2. CÁLCULOS MATEMÁTICOS ---

UMA_ANUAL = 39606.36
TOPE_5_UMAS = UMA_ANUAL * 5 
ISR_ESTIMADO = 0.30 

plazo_anos = retiro - edad
meses = plazo_anos * 12
data = []

saldo = 0
aporte_actual = ahorro_mensual
total_aportado = 0
acumulado_devoluciones = 0

tope_deducible_anual = TOPE_5_UMAS
if validar_sueldo and estrategia_fiscal == "Art 151 (PPR - Deducible)":
    tope_deducible_anual = min(TOPE_5_UMAS, sueldo_anual * 0.10)

for i in range(1, meses + 1):
    rendimiento_mensual = saldo * (tasa_interes / 12)
    saldo += rendimiento_mensual + aporte_actual
    total_aportado += aporte_actual
    
    if i % 12 == 0 and inflacion:
        aporte_actual *= (1 + tasa_inflacion)
    
    devolucion_anual = 0
    if estrategia_fiscal == "Art 151 (PPR - Deducible)":
        aporte_anual_proyectado = aporte_actual * 12
        monto_deducible = min(aporte_anual_proyectado, tope_deducible_anual)
        devolucion_anual = (monto_deducible * ISR_ESTIMADO) / 12 
        acumulado_devoluciones += devolucion_anual

    data.append({
        "Mes": i,
        "Año": edad + (i/12),
        "Saldo Neto": saldo,
        "Aportado": total_aportado,
        "Devoluciones SAT": acumulado_devoluciones * ((1+tasa_interes)**(plazo_anos - (i/12)))
    })

df = pd.DataFrame(data)

# --- 3. LÓGICA DE ALERTAS ---
aportacion_primer_ano = ahorro_mensual * 12
excedente = 0
mostrar_alerta = False
texto_alerta_pdf = ""

if estrategia_fiscal == "Art 151 (PPR - Deducible)":
    if aportacion_primer_ano > tope_deducible_anual:
        mostrar_alerta = True
        excedente = aportacion_primer_ano - tope_deducible_anual
        beneficio_sat_real = tope_deducible_anual * ISR_ESTIMADO
        texto_alerta_pdf = f"Tu aportación excede el tope deducible. Excedente no deducible: ${excedente:,.2f}"
    else:
        beneficio_sat_real = aportacion_primer_ano * ISR_ESTIMADO
else:
    beneficio_sat_real = 0 

# --- 4. INTERFAZ PRINCIPAL ---

st.title("🛡️ Simulador PPR")
st.markdown("Herramienta de proyección financiera realista.")

# Alerta Visual
if mostrar_alerta:
    st.warning(f"""
    ⚠️ **¡Atención! Tu aportación excede el límite deducible.**
    
    Estás aportando **\${aportacion_primer_ano:,.2f}** anuales.
    Toma en consideración que lo deducible son **\${tope_deducible_anual:,.2f}**.
    
    * Monto que SÍ deduce impuestos: **\${tope_deducible_anual:,.2f}**
    * Excedente (No deducible): **\${excedente:,.2f}**
    """)

# Métricas
col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="Total que aportas", value=f"${total_aportado:,.0f}")
with col2:
    st.metric(label="Saldo Final (Libre de comisiones)", value=f"${saldo:,.0f}", delta="Costo Admin incluido")
with col3:
    st.metric(label="Beneficio SAT Estimado (Total)", value=f"${beneficio_sat_real * plazo_anos:,.0f}", delta="Dinero que Hacienda te devuelve")

# Mensaje Fiscal
if estrategia_fiscal == "Art 93 (No Deducible)":
    st.success(f"""
    🌟 **Ventaja Fiscal (Art 93):** Aunque no deduces hoy, este plan garantiza que tus **${saldo:,.0f}** serán **Totalmente Libres de Impuestos** al recibirlos a los 60 años o más (según requisitos de permanencia).
    """)
    texto_analisis_pdf = "Plan Exento de Impuestos al final (Art 93 LISR). Recibes tu saldo íntegro."
elif estrategia_fiscal == "Art 151 (PPR - Deducible)":
    st.info("""
    ℹ️ **Consideración al Retiro:** Al finalizar el plan (edad 65), el monto acumulado es ingreso acumulable. Existe una exención grande (90 UMAs), pero el excedente podría pagar impuestos.
    """)
    texto_analisis_pdf = "Plan Deducible (Art 151 LISR). Genera devoluciones hoy, sujeto a retención al retiro sobre el excedente de 90 UMAs."

st.markdown("---")

# Gráfica
st.subheader("Proyección Real (Neto de Comisiones)")
df_chart = df[["Año", "Saldo Neto", "Aportado", "Devoluciones SAT"]].melt('Año', var_name='Categoría', value_name='Monto')

chart = alt.Chart(df_chart).mark_line().encode(
    x='Año',
    y='Monto',
    color=alt.Color('Categoría', scale=alt.Scale(domain=['Aportado', 'Saldo Neto', 'Devoluciones SAT'], range=['#ff4b4b', '#1f77b4', '#2ca02c'])),
    tooltip=['Año', 'Categoría', alt.Tooltip('Monto', format='$,.0f')]
).properties(height=400)

st.altair_chart(chart, use_container_width=True)

st.info("""
ℹ️ **Nota de Transparencia:** A diferencia de otros cotizadores, aquí **YA RESTAMOS** el costo administrativo 
(aprox 1.70% anual para tu nivel de aportación). Lo que ves en la línea azul es lo que realmente proyectamos que llegue a tu bolsillo.
""")

# --- 5. SECCIÓN DE DESCARGA PDF ---
st.markdown("### 📄 Exportar Propuesta")

if st.button("Generar PDF"):
    # Manejo del Logo Temporal
    logo_path_temp = None
    if uploaded_logo is not None:
        with open("temp_logo_upload.png", "wb") as f:
            f.write(uploaded_logo.getbuffer())
        logo_path_temp = "temp_logo_upload.png"
    
    # Generar PDF
    pdf_bytes, error = crear_pdf(
        {'nombre': nombre, 'edad': edad, 'retiro': retiro, 'estrategia': estrategia_fiscal},
        {'aporte_mensual': ahorro_mensual, 'saldo_final': saldo, 'beneficio_sat': beneficio_sat_real * plazo_anos},
        {'texto_analisis': texto_analisis_pdf, 'alerta_excedente': texto_alerta_pdf},
        {'nombre': asesor_nombre, 'telefono': asesor_telefono},
        logo_path_temp # Enviamos la ruta del logo
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
