import streamlit as st
import pandas as pd
import numpy as np
from fpdf import FPDF
import base64
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Simulador Krece360 Pro", layout="wide", page_icon="🛡️")

# --- ESTILOS VISUALES ---
st.markdown("""
    <style>
    .metric-card { background-color: #f0f2f6; border-left: 5px solid #2E86C1; padding: 15px; margin-bottom: 10px; border-radius: 5px;}
    .impuesto-alert { color: #943126; font-weight: bold; font-size: 14px;}
    .deduccion-success { color: #196F3D; font-weight: bold; font-size: 14px;}
    </style>
    """, unsafe_allow_html=True)

# --- CLASE PARA GENERAR PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Reporte de Proyección Financiera - Krece360', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Generado por Krece360 | Página {self.page_no()}', 0, 0, 'C')

def crear_pdf(datos_cliente, datos_financieros, df_tabla, agente_info):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Sección 1: Datos del Cliente
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(0, 10, "1. Perfil del Cliente", 0, 1, 'L', fill=True)
    pdf.ln(2)
    pdf.cell(0, 8, f"Nombre: {datos_cliente['nombre']}", 0, 1)
    pdf.cell(0, 8, f"Edad Actual: {datos_cliente['edad']} | Edad Retiro: {datos_cliente['retiro']}", 0, 1)
    pdf.cell(0, 8, f"Régimen Fiscal Elegido: {datos_cliente['regimen']}", 0, 1)
    pdf.ln(5)

    # Sección 2: Resumen Financiero
    pdf.cell(0, 10, "2. Proyección de Patrimonio (Estimado)", 0, 1, 'L', fill=True)
    pdf.ln(2)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(95, 10, "Total Aportado por ti:", 0, 0)
    pdf.set_font("Arial", size=12)
    pdf.cell(95, 10, f"${datos_financieros['aportado']:,.2f}", 0, 1)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(95, 10, "Saldo Final Estimado (Neto):", 0, 0)
    pdf.set_font("Arial", size=12)
    pdf.cell(95, 10, f"${datos_financieros['saldo']:,.2f}", 0, 1)
    
    if datos_financieros['beneficio_fiscal'] > 0:
        pdf.set_text_color(25, 111, 61) # Verde
        pdf.cell(0, 10, f"Beneficio Fiscal Estimado (Devoluciones SAT): ${datos_financieros['beneficio_fiscal']:,.2f}", 0, 1)
        pdf.set_text_color(0, 0, 0) # Reset color

    pdf.ln(5)
    
    # Sección 3: Transparencia de Costos
    pdf.cell(0, 10, "3. Transparencia de Costos y Comisiones", 0, 1, 'L', fill=True)
    pdf.ln(2)
    pdf.multi_cell(0, 8, f"Este cálculo ya contempla el costo administrativo aproximado de Allianz ({datos_financieros['tasa_admin']*100:.2f}% anual) según tu nivel de aportación. Mostramos valores netos para tu seguridad.")
    pdf.ln(5)

    # Sección 4: Contacto Agente
    pdf.ln(10)
    pdf.set_draw_color(46, 134, 193)
    pdf.set_line_width(1)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, f"Asesor Certificado: {agente_info['nombre']}", 0, 1, 'C')
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 8, f"Teléfono / WhatsApp: {agente_info['telefono']}", 0, 1, 'C')
    
    return pdf.output(dest='S').encode('latin-1')

# --- LÓGICA DE COSTOS ALLIANZ (Aproximación basada en PDF) ---
def obtener_tasa_admin(monto_mensual, plazo):
    # Lógica simplificada basada en la tabla de la página 9 del PDF
    # A mayor monto y plazo, menor tasa
    if monto_mensual < 3000:
        return 0.0228 # 2.28%
    elif monto_mensual < 6000:
        return 0.019 # Promedio 1.9%
    elif monto_mensual < 9000:
        return 0.017 # Promedio 1.7%
    else:
        return 0.0153 # 1.53% (Mínimo)

# --- APP STREAMLIT ---

st.title("🛡️ Simulador Krece360")
st.markdown("Herramienta de proyección financiera neta.")

col_main, col_sidebar = st.columns([3, 1])

with col_sidebar:
    st.header("⚙️ Parámetros")
    
    # Datos para el PDF
    st.subheader("Datos del Prospecto")
    nombre_cliente = st.text_input("Nombre Cliente", "Prospecto VIP")
    
    st.subheader("Configuración Plan")
    edad = st.number_input("Edad", 20, 65, 30)
    retiro = st.number_input("Edad Retiro", 55, 75, 65)
    plazo = retiro - edad
    
    ahorro = st.number_input("Ahorro Mensual", 1500, 50000, 2500, step=500)
    
    st.subheader("Fiscalidad y Rendimiento")
    regimen = st.selectbox("Estrategia Fiscal", 
                           ["Art 93 (No Deducible / Exento)", "Art 151 (PPR - Deducible)"])
    
    tasa_bruta = st.slider("Tasa Mercado Bruta (%)", 6.0, 14.0, 10.0) / 100
    inflacion = st.checkbox("Considerar Inflación (4%)", value=True)
    
    st.markdown("---")
    st.subheader("Datos del Agente")
    agente_nombre = st.text_input("Nombre Agente", "Araceli Torres Baez") # Default de tu PDF
    agente_tel = st.text_input("Teléfono", "55 1234 5678")

# --- CÁLCULOS ---
tasa_admin = obtener_tasa_admin(ahorro, plazo)
tasa_neta = tasa_bruta - tasa_admin # Restamos lo que cobra Allianz

datos = []
saldo = 0
aportado = 0
beneficio_fiscal_acumulado = 0
aporte_actual = ahorro

for i in range(1, (plazo * 12) + 1):
    # Ajuste inflacionario anual
    if inflacion and i > 1 and i % 12 == 0:
        aporte_actual *= 1.04 
    
    # Beneficio fiscal (Solo Art 151 - Aprox 30% de devolución anual)
    if regimen == "Art 151 (PPR - Deducible)" and i % 12 == 0:
        beneficio_fiscal_acumulado += (aporte_actual * 12) * 0.30

    # Interés compuesto con TASA NETA (Ya quitando cobro Allianz)
    saldo = (saldo + aporte_actual) * (1 + (tasa_neta / 12))
    aportado += aporte_actual
    
    if i % 12 == 0:
        datos.append({
            "Edad": edad + (i // 12),
            "Saldo Neto": saldo,
            "Aportado": aportado,
            "Devoluciones SAT": beneficio_fiscal_acumulado
        })

df = pd.DataFrame(datos).set_index("Edad")

# --- VISUALIZACIÓN PRINCIPAL ---
with col_main:
    # 1. Tarjetas de Resumen
    c1, c2, c3 = st.columns(3)
    saldo_final = df["Saldo Neto"].iloc[-1]
    aportado_final = df["Aportado"].iloc[-1]
    
    with c1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Total que aportas", f"${aportado_final:,.0f}")
        st.markdown('</div>', unsafe_allow_html=True)
        
    with c2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Saldo Final (Libre de comisiones)", f"${saldo_final:,.0f}", delta=f"Costo Admin: {tasa_admin*100:.2f}% incluído")
        st.markdown('</div>', unsafe_allow_html=True)

    with c3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        if regimen == "Art 151 (PPR - Deducible)":
            st.metric("Beneficio SAT Estimado", f"${beneficio_fiscal_acumulado:,.0f}")
            st.markdown('<span class="deduccion-success">Dinero que Hacienda te devuelve</span>', unsafe_allow_html=True)
        else:
            st.metric("Beneficio Fiscal", "Exento")
            st.markdown('<span class="deduccion-success">Todo el saldo final es libre de impuestos (Art 93)</span>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # 2. Gráfica
    st.subheader("Proyección Real (Neto de Comisiones)")
    
    # Preparamos los datos base (2 columnas)
    chart_data = df[["Aportado", "Saldo Neto"]]
    # Preparamos los colores base (Rojo y Azul)
    colores_grafica = ["#FF4B4B", "#2E86C1"]
    
    # Si es PPR, agregamos la 3er columna y el 3er color
    if regimen == "Art 151 (PPR - Deducible)":
        chart_data["Devoluciones SAT"] = df["Devoluciones SAT"]
        colores_grafica.append("#28B463") # Agregamos Verde solo si es necesario
        
    # Ahora sí, pasamos la lista de colores que coincida exactamente
    st.line_chart(chart_data, color=colores_grafica)

    # 3. Explicación de Transparencia
    st.info(f"""
    ℹ️ **Nota de Transparencia:** A diferencia de otros cotizadores, aquí **YA RESTAMOS** el costo administrativo de Allianz 
    (aprox {tasa_admin*100:.2f}% anual para tu nivel de aportación). 
    Lo que ves en la línea azul es lo que realmente proyectamos que llegue a tu bolsillo.
    """)

    # --- GENERACIÓN DE PDF ---
    st.markdown("---")
    st.subheader("📤 Descargar Propuesta")
    
    col_pdf, col_msg = st.columns([1, 2])
    
    datos_pdf_fin = {
        "aportado": aportado_final,
        "saldo": saldo_final,
        "beneficio_fiscal": beneficio_fiscal_acumulado if regimen == "Art 151 (PPR - Deducible)" else 0,
        "tasa_admin": tasa_admin
    }
    
    datos_pdf_cliente = {
        "nombre": nombre_cliente,
        "edad": edad,
        "retiro": retiro,
        "regimen": regimen
    }
    
    datos_agente = {
        "nombre": agente_nombre,
        "telefono": agente_tel
    }

    pdf_bytes = crear_pdf(datos_pdf_cliente, datos_pdf_fin, df, datos_agente)
    
    with col_pdf:
        st.download_button(
            label="📄 Descargar PDF Personalizado",
            data=pdf_bytes,
            file_name=f"Propuesta_Krece360_{nombre_cliente.replace(' ', '_')}.pdf",
            mime="application/pdf",
        )
    with col_msg:
        st.write("Entrega este documento a tu cliente. Incluye tus datos de contacto y el desglose transparente.")
