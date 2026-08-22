import datetime
import calendar
import os
import shutil
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import psycopg2
from sqlalchemy import create_engine

# 1. Configuración de página e Inyección de Tema Estético Institucional
st.set_page_config(
    page_title="Mi Trading Dashboard Cuantitativo", page_icon="📈", layout="wide"
)

# Crear carpeta local para almacenar imágenes temporalmente
CARPETA_IMAGENES = "capturas_trades"
if not os.path.exists(CARPETA_IMAGENES):
    os.makedirs(CARPETA_IMAGENES)

# === INYECCIÓN MAESTRA DE CSS (BLINDAJE TOTAL) ===
st.markdown("""
    <style>
        .stApp, [data-testid="stAppViewContainer"] { background-color: #070a13 !important; color: #FFFFFF !important; font-family: 'Inter', sans-serif !important; }
        [data-testid="stSidebar"] { background-color: #0b0f19 !important; border-right: 1px solid #222d4b !important; }
        [data-testid="stSidebar"] *, .stApp *, p, label, span, h1, h2, h3, h4, h5, h6 { color: #F8FAFC !important; }
        .stSelectbox div, .stTextInput input, .stNumberInput input, .stTextArea textarea, .stDateInput input, .stTimeInput input { background-color: #0f1524 !important; color: #FFFFFF !important; border: 1px solid #475d9a !important; font-weight: 700 !important; font-family: 'JetBrains Mono', monospace !important; }
        div[data-baseweb="input"], div[data-baseweb="input"] > div, div[data-baseweb="select"] > div { background-color: #0f1524 !important; color: #FFFFFF !important; border-color: #475d9a !important; }
        [data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"], div[data-testid="stNumberInput"] button, div[data-testid="stNumberInput"] div[role="button"] { background-color: #1e293b !important; color: #FFFFFF !important; border: 1px solid #475d9a !important; }
        [data-testid="stNumberInput"] svg, [data-testid="stTimeInput"] svg, [data-testid="stDateInput"] svg, div[data-baseweb="select"] svg { fill: #FFFFFF !important; color: #FFFFFF !important; }
        ::placeholder { color: #94A3B8 !important; opacity: 1 !important; }
        div[data-testid="metric-container"] { background-color: #0f1524 !important; border: 1px solid #283558 !important; padding: 16px 22px !important; border-radius: 10px !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5) !important; transition: all 0.3s ease; }
        div[data-testid="metric-container"]:hover { border-color: #475d9a !important; box-shadow: 0 6px 18px rgba(0, 0, 0, 0.7) !important; }
        div[data-testid="metric-container"] label { color: #CBD5E1 !important; font-size: 14px !important; font-weight: 700 !important; text-transform: uppercase !important; }
        div[data-testid="metric-container"] div[data-testid="stMetricValue"] { color: #FFFFFF !important; font-size: 28px !important; font-weight: 800 !important; font-family: 'JetBrains Mono', monospace !important; }
        button[data-baseweb="tab"] { color: #A1A1AA !important; font-weight: 700 !important; font-size: 15px !important; padding: 12px 20px !important; }
        button[data-baseweb="tab"]:hover { color: #FFFFFF !important; }
        button[data-baseweb="tab"][aria-selected="true"] { color: #00E676 !important; border-bottom-color: #00E676 !important; background-color: rgba(0, 230, 118, 0.08) !important; }
        button[kind="primary"] { background-color: #00E676 !important; color: #000000 !important; font-weight: 800 !important; font-size: 16px !important; border: none !important; box-shadow: 0 4px 12px rgba(0, 230, 118, 0.3) !important; }
        button[kind="primary"] * { color: #000000 !important; }
        button[kind="primary"]:hover { background-color: #00c862 !important; }
        div.stButton > button:not([kind="primary"]) { background-color: #7f1d1d !important; color: #FFFFFF !important; border: 1px solid #ef4444 !important; font-weight: 700 !important; }
        div.stButton > button:not([kind="primary"]) * { color: #FFFFFF !important; }
        div.stButton > button:not([kind="primary"]):hover { background-color: #991b1b !important; border-color: #f87171 !important; }
    </style>
""", unsafe_allow_html=True)


# 2. Conexión a Supabase (PostgreSQL)
URI = st.secrets["SUPABASE_URI"]
engine = create_engine(URI)

def get_conn():
    return psycopg2.connect(URI)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # Crear tablas en Supabase
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            fecha DATE,
            simbolo TEXT,
            activo TEXT,
            direccion TEXT,
            pnl REAL,
            estrategia TEXT,
            observaciones TEXT,
            comisiones REAL DEFAULT 0.0,
            hora TEXT DEFAULT '08:30',
            respeto_plan INTEGER DEFAULT 1,
            emocion TEXT DEFAULT 'Disciplinado',
            mae REAL DEFAULT 0.0,
            mfe REAL DEFAULT 0.0,
            r_multiple REAL DEFAULT 0.0,
            imagen_url TEXT DEFAULT ''
        )
    """)
    c.execute("CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS listas_guardadas (tipo TEXT, valor TEXT, PRIMARY KEY (tipo, valor))")
    conn.commit()
    conn.close()

init_db()

def get_config(clave, default_val):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT valor FROM config WHERE clave = %s", (clave,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default_val

def set_config(clave, valor):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO config (clave, valor) VALUES (%s, %s) 
        ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
    """, (clave, valor))
    conn.commit()
    conn.close()

def guardar_item_lista(tipo, valor):
    if not valor or str(valor).strip() == "": return
    conn = get_conn()
    c = conn.cursor()
    val_limpio = str(valor).strip().upper() if tipo == 'simbolo' else str(valor).strip()
    c.execute("""
        INSERT INTO listas_guardadas (tipo, valor) VALUES (%s, %s) 
        ON CONFLICT (tipo, valor) DO NOTHING
    """, (tipo, val_limpio))
    conn.commit()
    conn.close()

def eliminar_item_lista(tipo, valor):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM listas_guardadas WHERE tipo = %s AND valor = %s", (tipo, valor))
    conn.commit()
    conn.close()

def load_data():
    return pd.read_sql_query("SELECT * FROM trades ORDER BY fecha ASC, id ASC", engine)

df_base_previa = load_data()

simbolos_base = ["NQ", "ES", "AAPL", "SPY", "TSLA"]
estrategias_base = ["Breakout", "Squeeze", "Vertical Bull Put", "Swing Trade", "Order Flow"]

df_listas = pd.read_sql_query("SELECT * FROM listas_guardadas", engine)
simbolos_db = df_listas[df_listas["tipo"] == "simbolo"]["valor"].tolist()
estrategias_db = df_listas[df_listas["tipo"] == "estrategia"]["valor"].tolist()

if not df_base_previa.empty:
    if "simbolo" in df_base_previa.columns:
        simbolos_base += df_base_previa["simbolo"].dropna().unique().tolist()
    if "estrategia" in df_base_previa.columns:
        estrategias_base += df_base_previa["estrategia"].dropna().unique().tolist()

simbolos_finales = sorted(list(set(simbolos_base + simbolos_db)))
estrategias_finales = sorted(list(set(estrategias_base + estrategias_db)))

# --- SIDEBAR: REGISTRO DE DATOS ---
st.sidebar.title("⚙️ Panel de Control")
opcion_sidebar = st.sidebar.tabs(["📝 Entrada", "🔍 Filtros", "🗑️ Listas"])

with opcion_sidebar[0]:
    opcion_ingreso = st.radio("Selecciona método:", ["Manual (Uno a uno)", "Importar CSV / Excel"])

    if opcion_ingreso == "Manual (Uno a uno)":
        st.subheader("📝 Registro Manual")
        
        c_f1, c_f2 = st.columns(2)
        fecha = c_f1.date_input("Fecha de Cierre")
        hora = c_f2.time_input("Hora de Entrada", datetime.time(8, 30))
        
        opcion_simbolo = st.selectbox("Símbolo", simbolos_finales + ["➕ Añadir otro símbolo..."])
        simbolo_final = st.text_input("✍️ Escribe el Símbolo:").upper() if opcion_simbolo == "➕ Añadir otro símbolo..." else opcion_simbolo
        
        c_a1, c_a2 = st.columns(2)
        activo = c_a1.selectbox("Activo", ["FUTURO", "ACCIÓN", "OPCIÓN"])
        direccion = c_a2.selectbox("Dirección", ["LONG", "SHORT"])
        
        c_p1, c_p2 = st.columns(2)
        pnl = c_p1.number_input("P&L Neto ($)", step=10.0, format="%.2f")
        comisiones = c_p2.number_input("Comisiones ($)", value=4.10, step=0.50, format="%.2f")
        
        opcion_estrategia = st.selectbox("Estrategia / Etiqueta", estrategias_finales + ["➕ Añadir otra estrategia..."])
        estrategia_final = st.text_input("✍️ Escribe tu Estrategia:") if opcion_estrategia == "➕ Añadir otra estrategia..." else opcion_estrategia
        
        with st.expander("🖼️ Adjuntar Imagen / Captura de la Operación"):
            metodo_imagen = st.radio("Tipo de adjunto:", ["Enlace web (TradingView / Gyazo)", "Subir archivo de foto (.png/.jpg)"], horizontal=True)
            imagen_final_guardar = ""
            if metodo_imagen == "Enlace web (TradingView / Gyazo)":
                imagen_final_guardar = st.text_input("Enlace de tu captura:", placeholder="https://www.tradingview.com/x/...")
            else:
                foto_subida = st.file_uploader("Selecciona la imagen de tu computadora", type=["png", "jpg", "jpeg"])
                if foto_subida is not None:
                    # En la nube, guardar localmente no funciona bien a largo plazo.
                    # Se recomienda usar solo enlaces de TradingView.
                    st.warning("⚠️ Nota: En la versión web, las imágenes locales se borrarán al reiniciar el servidor. Es mejor usar enlaces web.")
                    nombre_archivo = f"trade_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{foto_subida.name}"
                    ruta_completa = os.path.join(CARPETA_IMAGENES, nombre_archivo)
                    with open(ruta_completa, "wb") as f:
                        f.write(foto_subida.getbuffer())
                    imagen_final_guardar = ruta_completa

        with st.expander("🧠 Psicología y Métricas Avanzadas (MFE/MAE/R)"):
            respeto_plan = st.checkbox("✅ Respeté mi plan de trading en esta entrada", value=True)
            emocion = st.selectbox("Estado Emocional:", ["Disciplinado", "Neutral", "FOMO (Miedo a perderse el movimiento)", "Venganza (Intentar recuperar)", "Ansioso / Dudoso"])
            c_m1, c_m2, c_m3 = st.columns(3)
            mae = c_m1.number_input("MAE ($ Flotante En Contra)", min_value=0.0, step=10.0, format="%.2f")
            mfe = c_m2.number_input("MFE ($ Flotante A Favor)", min_value=0.0, step=10.0, format="%.2f")
            r_multiple = c_m3.number_input("Resultado en R (ej. +2.0R)", step=0.25, format="%.2f")

        observaciones = st.text_area("📋 Razones de Entrada / Contexto:", placeholder="Setup técnico...")

        if st.button("Guardar Operación", type="primary", use_container_width=True):
            if not simbolo_final or str(simbolo_final).strip() == "":
                st.error("⚠️ Por favor selecciona un símbolo válido.")
            else:
                est_guardar = estrategia_final if (estrategia_final and str(estrategia_final).strip() != "") else "General"
                guardar_item_lista('simbolo', simbolo_final)
                guardar_item_lista('estrategia', est_guardar)
                
                conn = get_conn()
                c = conn.cursor()
                c.execute(
                    """INSERT INTO trades (fecha, simbolo, activo, direccion, pnl, estrategia, observaciones, comisiones, hora, respeto_plan, emocion, mae, mfe, r_multiple, imagen_url) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (fecha, str(simbolo_final).strip().upper(), activo, direccion, pnl, str(est_guardar).strip(), observaciones, comisiones, str(hora)[:5], 1 if respeto_plan else 0, emocion, mae, mfe, r_multiple, imagen_final_guardar),
                )
                conn.commit()
                conn.close()
                st.success(f"🎉 ¡{simbolo_final} guardado en la nube!")
                st.rerun()

    else:
        st.subheader("📥 Importador Inteligente")
        archivo_subido = st.file_uploader("Sube archivo masivo (CSV/Excel)", type=["csv", "xlsx"])

        if archivo_subido is not None:
            try:
                df_broker = pd.read_csv(archivo_subido) if archivo_subido.name.endswith(".csv") else pd.read_excel(archivo_subido)
                st.info(f"Archivo cargado: {len(df_broker)} filas detectadas.")
                st.dataframe(df_broker.head(3), use_container_width=True)
                col_fecha = st.selectbox("Columna de Fecha", df_broker.columns)
                col_simbolo = st.selectbox("Columna de Símbolo", df_broker.columns)
                col_pnl = st.selectbox("Columna de P&L Neto", df_broker.columns)
                tag_fijo = st.text_input("Etiqueta general", value="Importado")

                if st.button("🚀 Procesar e Importar"):
                    conn = get_conn()
                    c = conn.cursor()
                    registros_cargados = 0
                    for _, fila in df_broker.iterrows():
                        try:
                            f_val = pd.to_datetime(fila[col_fecha]).date()
                            s_val = str(fila[col_simbolo]).upper()
                            p_val = float(str(fila[col_pnl]).replace("$", "").replace(",", ""))
                            guardar_item_lista('simbolo', s_val)
                            guardar_item_lista('estrategia', tag_fijo)
                            c.execute(
                                """INSERT INTO trades (fecha, simbolo, activo, direccion, pnl, estrategia, observaciones, comisiones, hora, respeto_plan, emocion, mae, mfe, r_multiple, imagen_url) 
                                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                                (f_val, s_val, "FUTURO", "LONG", p_val, tag_fijo, "Importación masiva", 0.0, "08:30", 1, "Disciplinado", 0.0, 0.0, 0.0, ""),
                            )
                            registros_cargados += 1
                        except Exception:
                            continue
                    conn.commit()
                    conn.close()
                    if registros_cargados > 0:
                        st.success(f"🎉 ¡Se importaron {registros_cargados} operaciones a la nube!")
                        st.rerun()
            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")

df_base = load_data()
with opcion_sidebar[1]:
    st.subheader("🔍 Filtrar Dashboard")
    if not df_base.empty:
        filtro_activo = st.selectbox("Clase de Activo:", ["Todos"] + list(df_base["activo"].unique()))
        filtro_direccion = st.selectbox("Dirección:", ["Todos"] + list(df_base["direccion"].unique()))
        filtro_estrategia = st.selectbox("Estrategia / Tag:", ["Todos"] + list(df_base["estrategia"].unique()))
    else:
        st.write("No hay datos para filtrar.")

with opcion_sidebar[2]:
    st.subheader("🗑️ Limpiar Desplegables")
    simbolo_a_borrar = st.selectbox("Quitar Símbolo:", ["(Ninguno)"] + simbolos_finales)
    if st.button("❌ Quitar Símbolo") and simbolo_a_borrar != "(Ninguno)":
        eliminar_item_lista('simbolo', simbolo_a_borrar)
        st.success("Símbolo eliminado.")
        st.rerun()
            
    st.divider()
    est_a_borrar = st.selectbox("Quitar Estrategia:", ["(Ninguno)"] + estrategias_finales)
    if st.button("❌ Quitar Estrategia") and est_a_borrar != "(Ninguno)":
        eliminar_item_lista('estrategia', est_a_borrar)
        st.success("Estrategia eliminada.")
        st.rerun()

df = df_base.copy()
if not df.empty:
    if filtro_activo != "Todos": df = df[df["activo"] == filtro_activo]
    if filtro_direccion != "Todos": df = df[df["direccion"] == filtro_direccion]
    if filtro_estrategia != "Todos": df = df[df["estrategia"] == filtro_estrategia]
    
    df["comisiones"] = df["comisiones"].fillna(0.0)
    df["pnl_bruto"] = df["pnl"] + df["comisiones"]
    df["hora"] = df["hora"].fillna("08:30")
    df["respeto_plan"] = df["respeto_plan"].fillna(1)
    df["emocion"] = df["emocion"].fillna("Disciplinado")
    df["mae"] = df["mae"].fillna(0.0)
    df["mfe"] = df["mfe"].fillna(0.0)
    df["r_multiple"] = df["r_multiple"].fillna(0.0)
    if "imagen_url" not in df.columns:
        df["imagen_url"] = ""
    df["imagen_url"] = df["imagen_url"].fillna("")

# --- INTERFAZ PRINCIPAL ---
st.title("📈 Dashboard Cuantitativo de Trading - Nube")

if not df.empty:
    df["fecha"] = pd.to_datetime(df["fecha"])
    hoy = pd.to_datetime(datetime.date.today()).date()
    trades_hoy = df[df["fecha"].dt.date == hoy]
    
    pos_hoy = len(trades_hoy[trades_hoy["pnl"] > 5.0])
    neg_hoy = len(trades_hoy[trades_hoy["pnl"] < -5.0])
    be_hoy = len(trades_hoy[(trades_hoy["pnl"] >= -5.0) & (trades_hoy["pnl"] <= 5.0)])
    total_hoy = len(trades_hoy)
    
    daily_pnl_conciencia = df.groupby(df["fecha"].dt.date)["pnl"].sum().reset_index()
    daily_pnl_conciencia = daily_pnl_conciencia.sort_values(by="fecha", ascending=False)
    
    racha_dias_pos, racha_dias_neg = 0, 0
    for _, fila_d in daily_pnl_conciencia.iterrows():
        if fila_d["pnl"] > 10.0:
            if racha_dias_neg > 0: break
            racha_dias_pos += 1
        elif fila_d["pnl"] < -10.0:
            if racha_dias_pos > 0: break
            racha_dias_neg += 1
        else:
            break

    with st.container():
        if racha_dias_neg >= 3:
            st.error("🛑 **ALERTA DE RACHA SEMANAL:** Termina tu semana operativa. ¡Protege tu cuenta!")
        elif racha_dias_pos >= 3:
            st.success("🏁 **ALERTA DE RACHA SEMANAL:** Termina tu semana operativa. ¡Asegura lo ganado!")
        elif racha_dias_pos == 2 or racha_dias_neg == 2:
            st.warning("⏸️ **EVALUACIÓN:** Tómate 24 horas libres.")
        elif total_hoy > 0:
            if pos_hoy >= 2 or neg_hoy >= 2:
                st.error("🛑 **REGLA INTRADÍA (Límite Alcanzado):** No tienes permiso de operar más hoy.")
            elif be_hoy >= 2:
                st.warning("🧘 **REGLA INTRADÍA (Breakeven):** Toma 20 minutos de descanso antes del último trade.")
            else:
                st.info("🟢 **ESTADO INTRADÍA:** Permiso para un trade extra opcional.")

capital_inicial_db = get_config("capital_inicial", 10000.0)
pnl_total = df['pnl'].sum() if not df.empty else 0.0
capital_al_dia = capital_inicial_db + pnl_total

if df_base.empty:
    st.info("👋 Base de datos vacía. Sincronizando con Supabase...")
elif df.empty:
    st.warning("⚠️ Sin operaciones para los filtros actuales.")
else:
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.sort_values(by=["fecha", "id"])
    
    col_t1, col_t2 = st.columns([1, 4])
    with col_t1:
        vista_tiempo = st.selectbox("⏳ Filtro de Período:", ["Todo el Historial", "Este Año", "Este Mes", "Esta Semana", "Hoy"])
    
    hoy_dt = pd.to_datetime(datetime.date.today())
    if vista_tiempo == "Hoy": df_vista = df[df["fecha"].dt.date == hoy_dt.date()]
    elif vista_tiempo == "Esta Semana": df_vista = df[df["fecha"] >= (hoy_dt - pd.to_timedelta(hoy_dt.dayofweek, unit='d'))]
    elif vista_tiempo == "Este Mes": df_vista = df[(df["fecha"].dt.year == hoy_dt.year) & (df["fecha"].dt.month == hoy_dt.month)]
    elif vista_tiempo == "Este Año": df_vista = df[df["fecha"].dt.year == hoy_dt.year]
    else: df_vista = df.copy()

    df_vista["curva_neta"] = df_vista["pnl"].cumsum()
    df_vista["curva_bruta"] = df_vista["pnl_bruto"].cumsum()
    pnl_vista = df_vista['pnl'].sum() if not df_vista.empty else 0.0
    comisiones_totales = df_vista['comisiones'].sum() if not df_vista.empty else 0.0
    picos = np.maximum(df_vista["curva_neta"].cummax(), 0) if not df_vista.empty else pd.Series([0])
    max_drawdown = (df_vista["curva_neta"] - picos).min() if not df_vista.empty else 0.0
    ganadores, perdedores = df_vista[df_vista["pnl"] > 0], df_vista[df_vista["pnl"] < 0]
    win_rate = (len(ganadores) / len(df_vista)) * 100 if len(df_vista) > 0 else 0
    profit_factor = ganadores["pnl"].sum() / abs(perdedores["pnl"].sum()) if len(perdedores) > 0 else ganadores["pnl"].sum()

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("P&L Neto", f"${pnl_vista:,.2f}")
    col2.metric("Comisiones", f"${comisiones_totales:,.2f}")
    col3.metric("Win Rate", f"{win_rate:.1f}%")
    col4.metric("Profit Factor", f"{profit_factor:.2f}")
    col5.metric("Operaciones", f"{len(df_vista)}")
    col6.metric("Max Drawdown", f"${max_drawdown:,.2f}", delta_color="inverse")
    st.divider()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📈 Dashboard & Calendario", "🧠 Psicología & Horarios", "🔬 Cuantitativo (MAE/MFE & R)", "📊 Estrategias", "🛡️ Gestión de Riesgo", "📋 Bitácora & Capturas"])

    with tab1:
        if not df_vista.empty:
            df_equity_melted = df_vista.melt(id_vars=["fecha"], value_vars=["curva_neta", "curva_bruta"], var_name="Tipo", value_name="Capital Acumulado")
            fig_equity = px.line(df_equity_melted, x="fecha", y="Capital Acumulado", color="Tipo", title=f"Evolución de Equidad ({vista_tiempo})", markers=True)
            fig_equity.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color="#FFFFFF"))
            st.plotly_chart(fig_equity, use_container_width=True)

    with tab2:
        df_vista["franja_hora"] = df_vista["hora"].str[:2] + ":00"
        pnl_hora = df_vista.groupby("franja_hora")["pnl"].sum().reset_index()
        fig_hora = px.bar(pnl_hora, x="franja_hora", y="pnl", title="Rendimiento por Horario")
        fig_hora.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color="#FFFFFF"))
        st.plotly_chart(fig_hora, use_container_width=True)

    with tab3:
        if df_vista["mfe"].sum() > 0 or df_vista["mae"].sum() > 0:
            df_vista["Resultado"] = np.where(df_vista["pnl"] > 0, "Ganadora", "Perdedora")
            fig_mae = px.scatter(df_vista, x="mae", y="mfe", color="Resultado", size=abs(df_vista["pnl"]) + 10, hover_data=["simbolo", "estrategia", "pnl"])
            fig_mae.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color="#FFFFFF"))
            st.plotly_chart(fig_mae, use_container_width=True)
        else: st.info("Registra el MAE y MFE en el panel para ver la dispersión.")

    with tab4:
        pnl_estrategia = df_vista.groupby("estrategia")["pnl"].sum().reset_index()
        fig_bar = px.bar(pnl_estrategia, x="estrategia", y="pnl", text_auto='.2s')
        fig_bar.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color="#FFFFFF"))
        st.plotly_chart(fig_bar, use_container_width=True)

    with tab5:
        st.subheader("🛡️ Gestión y Protección del Capital")
        col_c1, col_c2, col_c3 = st.columns([1, 1, 1])
        with col_c1:
            nuevo_cap = st.number_input("💰 Capital Inicial ($)", value=float(capital_inicial_db), step=100.0, format="%.2f")
            if nuevo_cap != capital_inicial_db: set_config("capital_inicial", nuevo_cap); st.rerun()
        with col_c2: st.metric("📈 Capital al Día", f"${capital_al_dia:,.2f}", delta=f"{pnl_total:,.2f} P&L")
        with col_c3: st.metric("🚀 Rendimiento Total", f"{(pnl_total / capital_inicial_db) * 100 if capital_inicial_db > 0 else 0:+.2f}%")

    with tab6:
        st.subheader("📋 Bitácora Completa, Capturas y Exportación")
        col_btn1, col_btn2 = st.columns([2, 1])
        with col_btn1:
            csv_export = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Descargar CSV Auditado", data=csv_export, file_name="trading_journal.csv", mime="text/csv", type="primary")
        with col_btn2:
            if st.button("🔴 Borrar Todo el Historial", use_container_width=True):
                conn = get_conn()
                conn.cursor().execute("DELETE FROM trades")
                conn.commit(); conn.close()
                st.rerun()
                
        df_para_mostrar = df.drop(columns=["id"]).copy()
        st.dataframe(df_para_mostrar, use_container_width=True)