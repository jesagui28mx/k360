import streamlit as st
import pandas as pd
import numpy as np
from fpdf import FPDF
import base64

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Krece360 Debug", layout="wide", page_icon="🛠️")

# --- CLASE PDF ROBUSTA (SIN LOGO SI FALLA) ---
class PDFReport(FPDF):
    def header(self):
        try:
            # Intenta cargar logo.png, si falla, sigue sin logo
            self.image('logo.png', 10, 8, 33) 
        except Exception as e:
            pass # Ignoramos error de logo para que no rompa el PDF
            
        self.set_font('Arial', 'B', 15)
        self.cell(40) 
        self.cell(0, 10, 'Krece360 - Proyección', 0, 1, 'L')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def crear_pdf_seguro(datos_cliente, datos_fin, df, datos_agente):
    try:
        pdf = PDFReport()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        # Texto simple para probar
        pdf.cell(0, 10, f"Cliente: {datos_cliente['nombre']}", 0, 1)
        pdf.cell(0, 10, f"Saldo Final Estimado: ${datos_fin['saldo']:,.2f}", 0, 1)
        
        if datos_fin['mensaje_fiscal']:
            pdf.set_text_color(200, 0, 0)
            pdf.multi_cell(0, 10, f"Nota: {datos_fin['mensaje_fiscal']}")
            pdf.set_text_color(0, 0, 0)
            
        pdf.ln(10)
        pdf.cell(0, 10, f"Asesor: {datos_agente['nombre']}", 0, 1)
        
        # Retorno seguro
        return pdf.output(dest='S').encode('latin-1', 'replace'), None
    except Exception as e:
        return None, str(e)

# --- INTERFAZ ---
st.title("🛠️ Modo Diagnóstico Krece360")

col1, col2 = st.columns([1, 2])

with col1:
    st.header("1. Inputs")
    regimen = st.selectbox("Régimen", ["Art 93", "Art 151 (PPR)"])
    ahorro = st.number_input("Ahorro", value=8000)
    edad = st.number_input("Edad", value=30)
    retiro = st.number_input("Retiro", value=65)
    tasa = 0.10
    
    # Checkbox forzado para debug
    st.info(f"Seleccionaste: {regimen}")

# --- CÁLCULOS SIMPLIFICADOS PARA DEBUG ---
plazo = retiro - edad
saldo = 0
aporte = ahorro
tope_ppr = 3714612

for i in range(1, plazo*12 + 1):
    saldo = (saldo + aporte) * (1 + tasa/12)
    if i % 12 == 0: aporte *= 1.04 # Inflación

# Lógica de Alerta
alerta_texto = ""
alerta_tipo = "success"

if regimen == "Art 151 (PPR)":
    if saldo > tope_ppr:
        alerta_texto = f"⚠️ ALERTA NARANJA ACTIVADA: Saldo ${saldo:,.0f} > Tope ${tope_ppr:,.0f}"
        alerta_tipo = "warning"
    else:
        alerta_texto = "✅ VERDE: Saldo menor al tope (PPR)"
else:
    alerta_texto = "✅ VERDE: Art 93 no tiene tope de monto"

# --- RESULTADOS ---
with col2:
    st.header("2. Resultados del Diagnóstico")
    st.write(f"Saldo Final Calculado: **${saldo:,.2f}**")
    
    if alerta_tipo == "warning":
        st.warning(alerta_texto)
    else:
        st.success(alerta_texto)
        
    st.markdown("---")
    st.subheader("3. Prueba de PDF")
    
    # Generar PDF
    pdf_bytes, error = crear_pdf_seguro(
        {'nombre': 'Test', 'nombre': 'Test', 'edad': edad, 'retiro': retiro, 'regimen': regimen},
        {'saldo': saldo, 'mensaje_fiscal': alerta_texto},
        None,
        {'nombre': 'Agente', 'telefono': '555'}
    )
    
    if error:
        st.error(f"❌ ERROR generando PDF: {error}")
    else:
        st.download_button("Descargar PDF de Prueba", data=pdf_bytes, file_name="test.pdf", mime="application/pdf")
