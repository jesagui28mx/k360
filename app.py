import streamlit as st
import pandas as pd
import numpy as np
from fpdf import FPDF
import base64

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Krece360 Debug", layout="wide", page_icon="🛠️")

# --- CONSTANTES FISCALES (2024) ---
UMA_DIARIA = 108.57
UMA_ANUAL = UMA_DIARIA * 30.4 * 12  # Aprox 39,606.36
TOPE_5_UMAS = UMA_ANUAL * 5         # Aprox 198,031.80

# --- CLASE PDF ROBUSTA ---
class PDFReport(FPDF):
    def header(self):
        try:
            self.image('logo.png', 10, 8, 33) 
        except Exception:
            pass 
        self.set_font('Arial', 'B', 15)
        self.cell(40) 
        self.cell(0, 10, 'Krece360 - Proyección', 0, 1, 'L')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def crear_pdf_seguro(datos_cliente, datos_fin, datos_agente):
    try:
        pdf = PDFReport()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        pdf.cell(0, 10, f"Cliente: {datos_cliente['nombre']}", 0, 1)
        pdf.cell(0, 10, f"Plan: {datos_cliente['regimen']}", 0, 1)
        pdf.ln(5)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"Saldo Final Estimado: ${datos_fin['saldo']:,.2f}", 0, 1)
        pdf.set_font("Arial", size=12)
        
        # Sección de Análisis Fiscal en el PDF
        pdf.ln(5)
        pdf.cell(0, 10, "--- Análisis de Deducibilidad (Anual) ---", 0, 1)
        pdf.cell(0, 10, f"Aportación Anual: ${datos_fin['aportacion_anual']:,.2f}", 0, 1)
        pdf.cell(0, 10, f"Tope Deducible Aplicado: ${datos_fin['tope_deducible']:,.2f}", 0, 1)
        
        if datos_fin['monto_no_deducible'] > 0:
            pdf.set_text_color(200, 0, 0) # Rojo para advertencias
            pdf.multi_cell(0, 10, f"AVISO: Tienes un excedente NO deducible de ${datos_fin['monto_no_deducible']:,.2f} anuales.")
        else:
            pdf.set_text_color(0, 128, 0) # Verde
            pdf.cell(0, 10, "Tu aportación es 100% deducible.", 0, 1)
            
        pdf.set_text_color(0, 0, 0) # Reset color
        pdf.ln(10)
        pdf.cell(0, 10, f"Asesor: {datos_agente['nombre']}", 0, 1)
        
        return pdf.output(dest='S').encode('latin-1', 'replace'), None
    except Exception as e:
        return None, str(e)

# --- INTERFAZ ---
st.title("🛠️ Simulador Krece360 - Módulo Fiscal")

col1, col2 = st.columns([1, 2])

with col1:
    st.header("1. Datos del Plan")
    regimen = st.selectbox("Régimen Fiscal", ["Art 93 (No Deducible)", "Art 151 (PPR Deducible)"])
    ahorro_mensual = st.number_input("Ahorro Mensual", value=8000, step=500)
    edad = st.number_input("Edad Actual", value=30)
    retiro = st.number_input("Edad de Retiro", value=65)
    
    # --- LÓGICA DEL SCRIPT NUEVO: INPUT CONDICIONAL ---
    sueldo_anual = 0
    validar_sueldo = False
    
    if regimen == "Art 151 (PPR Deducible)":
        st.markdown("---")
        st.subheader("Configuración Fiscal")
        validar_sueldo = st.checkbox("¿Validar tope con Sueldo Anual?", value=False)
        
        if validar_sueldo:
            sueldo_anual = st.number_input("Sueldo Bruto Anual Estimado", value=600000, step=10000)
            st.caption(f"El 10% de tu sueldo es: ${sueldo_anual*0.10:,.2f}")
        else:
            st.info("Se usará el tope estándar de 5 UMAs ($198k aprox) sin considerar el sueldo.")

# --- CÁLCULOS ---
# 1. Proyección Financiera Básica
tasa = 0.10
plazo = retiro - edad
saldo = 0
aporte = ahorro_mensual
aportacion_anual_total = ahorro_mensual * 12

for i in range(1, plazo*12 + 1):
    saldo = (saldo + aporte) * (1 + tasa/12)
    if i % 12 == 0: aporte *= 1.04 # Inflación

# 2. Lógica de Deducibilidad (LO NUEVO)
tope_real_aplicable = 0
monto_deducible = 0
monto_no_deducible = 0
mensaje_fiscal_ui = ""
tipo_alerta = "success"

if regimen == "Art 151 (PPR Deducible)":
    # Definimos el tope
    tope_5_umas = TOPE_5_UMAS
    tope_10_ingreso = sueldo_anual * 0.10 if validar_sueldo else float('inf')
    
    # El tope es el MENOR de los dos criterios
    if validar_sueldo:
        tope_real_aplicable = min(tope_5_umas, tope_10_ingreso)
        criterio = "10% de Ingresos" if tope_10_ingreso < tope_5_umas else "5 UMAs Anuales"
    else:
        tope_real_aplicable = tope_5_umas
        criterio = "5 UMAs Anuales (Estándar)"

    # Calculamos excedentes
    if aportacion_anual_total > tope_real_aplicable:
        monto_deducible = tope_real_aplicable
        monto_no_deducible = aportacion_anual_total - tope_real_aplicable
        tipo_alerta = "warning"
        mensaje_fiscal_ui = f"""
        ⚠️ **Atención:** Tu aportación anual (${aportacion_anual_total:,.2f}) excede tu tope deducible.
        
        * Tope aplicado ({criterio}): **${tope_real_aplicable:,.2f}**
        * Monto que SÍ deduces: **${monto_deducible:,.2f}**
        * Excedente (No deducible): **${monto_no_deducible:,.2f}**
        """
    else:
        monto_deducible = aportacion_anual_total
        tipo_alerta = "success"
        mensaje_fiscal_ui = f"✅ Tu aportación anual (${aportacion_anual_total:,.2f}) es 100% deducible dentro del tope de {criterio}."

else:
    # Art 93
    mensaje_fiscal_ui = "ℹ️ El Art 93 no tiene límite de aportación (No es deducible, es exento al final)."
    tope_real_aplicable = 0 # No aplica

# --- RESULTADOS ---
with col2:
    st.header("2. Diagnóstico Fiscal y Financiero")
    
    # Tarjetas de resumen
    c1, c2 = st.columns(2)
    c1.metric("Saldo al Retiro (Estimado)", f"${saldo:,.0f}")
    c2.metric("Aportación Anual Total", f"${aportacion_anual_total:,.0f}")
    
    st.markdown("### Análisis de Impuestos")
    
    if tipo_alerta == "warning":
        st.warning(mensaje_fiscal_ui)
    else:
        st.success(mensaje_fiscal_ui)
        
    st.markdown("---")
    st.subheader("3. Exportar Propuesta")
    
    # Datos para el PDF
    datos_fin_pdf = {
        'saldo': saldo,
        'aportacion_anual': aportacion_anual_total,
        'tope_deducible': tope_real_aplicable if regimen == "Art 151 (PPR Deducible)" else 0,
        'monto_no_deducible': monto_no_deducible
    }
    
    pdf_bytes, error = crear_pdf_seguro(
        {'nombre': 'Prospecto Cliente', 'regimen': regimen, 'edad': edad, 'retiro': retiro},
        datos_fin_pdf,
        {'nombre': 'Tu Nombre', 'telefono': '555-000-0000'}
    )
    
    if error:
        st.error(f"❌ Error PDF: {error}")
    else:
        st.download_button("Descargar PDF", data=pdf_bytes, file_name="simulacion_fiscal.pdf", mime="application/pdf")
