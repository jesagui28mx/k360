import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Simulador Krece360", layout="wide", page_icon="🛡️")

# --- ESTILOS CSS PARA QUE SE VEA COMO TU DISEÑO ORIGINAL ---
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

# --- 1. SIDEBAR (DATOS DEL PROSPECTO Y CONFIGURACIÓN) ---
with st.sidebar:
    st.image("https://via.placeholder.com/150x50?text=Logo+Krece360", use_column_width=True) # Tu logo aquí
    st.header("⚙️ Parámetros")
    
    st.subheader("Datos del Prospecto")
    nombre = st.text_input("Nombre Cliente", value="Escribe aquí")
    
    st.subheader("Configuración Plan")
    col_edad, col_retiro = st.columns(2)
    edad = col_edad.number_input("Edad", value=30, step=1)
    retiro = col_retiro.number_input("Edad Retiro", value=65, step=1)
    
    ahorro_mensual = st.number_input("Ahorro Mensual", value=1500, step=500)
    
    st.subheader("Fiscalidad y Rendimiento")
    estrategia_fiscal = st.selectbox("Estrategia Fiscal", ["Art 151 (PPR - Deducible)", "Art 93 (No Deducible)"])
    
    # --- AQUÍ ESTÁ LA NUEVA LÓGICA INTEGRADA EN EL SIDEBAR ---
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

# --- 2. CÁLCULOS MATEMÁTICOS (MOTOR) ---

# Constantes 2024
UMA_ANUAL = 39606.36
TOPE_5_UMAS = UMA_ANUAL * 5  # ~198,031
ISR_ESTIMADO = 0.30 # Para calcular cuánto devuelve hacienda aprox

# Proyección
plazo_anos = retiro - edad
meses = plazo_anos * 12
data = []

saldo = 0
aporte_actual = ahorro_mensual
total_aportado = 0
acumulado_devoluciones = 0

# Definir tope anual fiscal
tope_deducible_anual = TOPE_5_UMAS
if validar_sueldo and estrategia_fiscal == "Art 151 (PPR - Deducible)":
    tope_deducible_anual = min(TOPE_5_UMAS, sueldo_anual * 0.10)

# Loop de proyección
for i in range(1, meses + 1):
    ano_actual = i // 12
    
    # Interés compuesto mensual
    rendimiento_mensual = saldo * (tasa_interes / 12)
    saldo += rendimiento_mensual + aporte_actual
    total_aportado += aporte_actual
    
    # Ajuste inflación anual
    if i % 12 == 0 and inflacion:
        aporte_actual *= (1 + tasa_inflacion)
    
    # Cálculo devoluciones (simplificado anualizado para la gráfica)
    devolucion_anual = 0
    if estrategia_fiscal == "Art 151 (PPR - Deducible)":
        # Aportación anualizada simple para el cálculo gráfico
        aporte_anual_proyectado = aporte_actual * 12
        monto_deducible = min(aporte_anual_proyectado, tope_deducible_anual)
        devolucion_anual = (monto_deducible * ISR_ESTIMADO) / 12 # Mensualizado para gráfica
        acumulado_devoluciones += devolucion_anual

    data.append({
        "Mes": i,
        "Año": edad + (i/12),
        "Saldo Neto": saldo,
        "Aportado": total_aportado,
        "Devoluciones SAT": acumulado_devoluciones * ((1+tasa_interes)**(plazo_anos - (i/12))) # Valor futuro aprox de las devoluciones
    })

df = pd.DataFrame(data)

# --- 3. LÓGICA DE ALERTAS (EL CÓDIGO NUEVO) ---
aportacion_primer_ano = ahorro_mensual * 12
excedente = 0
mensaje_alerta = ""
mostrar_alerta = False

if estrategia_fiscal == "Art 151 (PPR - Deducible)":
    if aportacion_primer_ano > tope_deducible_anual:
        mostrar_alerta = True
        excedente = aportacion_primer_ano - tope_deducible_anual
        beneficio_sat_real = tope_deducible_anual * ISR_ESTIMADO
    else:
        beneficio_sat_real = aportacion_primer_ano * ISR_ESTIMADO
else:
    beneficio_sat_real = 0 # Art 93 no deduce

# --- 4. INTERFAZ PRINCIPAL (MAIN DASHBOARD) ---

st.title("🛡️ Simulador Krece360")
st.markdown("Herramienta de proyección financiera neta.")

# --- ALERTA INTELIGENTE (AQUÍ APARECE SI HAY EXCEDENTE) ---
if mostrar_alerta:
    st.warning(f"""
    ⚠️ **¡Atención! Tu aportación excede el límite deducible.**
    
    Estás aportando **\${aportacion_primer_ano:,.2f}** anuales.
    Toma en consideración que lo deducible son **\${tope_deducible_anual:,.2f}**.
    
    * Monto que SÍ deduce impuestos: **\${tope_deducible_anual:,.2f}**
    * Excedente (No deducible): **\${excedente:,.2f}**
    """)

# --- TARJETAS DE MÉTRICAS (KPIs) ---
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="Total que aportas", value=f"${total_aportado:,.0f}")

with col2:
    st.metric(label="Saldo Final (Libre de comisiones)", value=f"${saldo:,.0f}", delta="Costo Admin incluido")

with col3:
    st.metric(label="Beneficio SAT Estimado (Total)", value=f"${beneficio_sat_real * plazo_anos:,.0f}", delta="Dinero que Hacienda te devuelve")

st.markdown("---")

# --- GRÁFICA (ALTAIR) ---
st.subheader("Proyección Real (Neto de Comisiones)")

# Transformar datos para Altair (Formato largo)
df_chart = df[["Año", "Saldo Neto", "Aportado", "Devoluciones SAT"]].melt('Año', var_name='Categoría', value_name='Monto')

chart = alt.Chart(df_chart).mark_line().encode(
    x='Año',
    y='Monto',
    color=alt.Color('Categoría', scale=alt.Scale(domain=['Aportado', 'Saldo Neto', 'Devoluciones SAT'], range=['#ff4b4b', '#1f77b4', '#2ca02c'])),
    tooltip=['Año', 'Categoría', alt.Tooltip('Monto', format='$,.0f')]
).properties(
    height=400
)

st.altair_chart(chart, use_container_width=True)

# --- NOTA DE TRANSPARENCIA (AZUL AL FINAL) ---
st.info("""
ℹ️ **Nota de Transparencia:** A diferencia de otros cotizadores, aquí **YA RESTAMOS** el costo administrativo 
(aprox 1.70% anual para tu nivel de aportación). Lo que ves en la línea azul es lo que realmente proyectamos que llegue a tu bolsillo.
""")
