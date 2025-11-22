import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import altair as alt
from datetime import datetime, timedelta
import json

# ==========================================
# CONFIGURACIÓN GENERAL DE LA APP
# ==========================================
st.set_page_config(page_title="Dashboard Ventas", layout="wide")

# ==========================================
# 0) AUTENTICACIÓN SIMPLE CON SECRETO
# ==========================================
USERS = ["darlet", "wirbi"]
PASSWORD = st.secrets["APP_PASSWORD"]  # ✅ contraseña segura en secrets.toml

def login_screen():
    st.title("🔐 Inicio de Sesión")
    st.write("Ingrese sus credenciales para continuar")

    user = st.text_input("Usuario")
    pwd = st.text_input("Contraseña", type="password")

    if st.button("Ingresar"):
        if user in USERS and pwd == PASSWORD:
            st.session_state["logged_in"] = True
            st.session_state["user"] = user
            st.success("Ingreso exitoso 🎉")
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos")

if "logged_in" not in st.session_state or st.session_state["logged_in"] is False:
    login_screen()
    st.stop()

# ==========================================
# 1) CARGA DE DATOS — DETECTAR AÑO ACTUAL
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive",
    ]

    # ✅ Usar service account desde secrets
    sa_info = st.secrets["SERVICE_ACCOUNT"]  # JSON como diccionario
    creds = ServiceAccountCredentials.from_json_keyfile_dict(sa_info, scope)
    client = gspread.authorize(creds)

    sh = client.open("pedidos_darla")
    current_year = str(datetime.now().year)
    ws = sh.worksheet(current_year)

    data = ws.get_all_records()
    df = pd.DataFrame(data)
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors='coerce', dayfirst=True).dt.normalize()
    return df

df = load_data()
st.title("📊 Dashboard de Ventas")

# ==========================================
# 2) MENÚ LATERAL
# ==========================================
menu = st.sidebar.radio(
    "📌 Selecciona una vista",
    ["🏠 Dashboard General", "👥 Clientes", "📦 Productos", "🧾 Ventas"]
)
st.sidebar.markdown("---")
st.sidebar.write(f"👤 Usuario: **{st.session_state['user']}**")

# ==========================================
# 3) FILTRO GLOBAL DE FECHAS
# ==========================================
st.sidebar.markdown("### 🔍 Filtros globales")
today = datetime.now().date()
week_ago = today - timedelta(days=7)
min_date_db = df["Fecha"].min().date()
max_date_db = df["Fecha"].max().date()
default_start = max(min_date_db, week_ago)
default_end = today

date_range = st.sidebar.date_input("Rango de fechas", [default_start, default_end])
if not isinstance(date_range, (list, tuple)) or len(date_range) != 2:
    st.sidebar.error("Selecciona un rango válido.")
    df_filtrado = df.iloc[0:0]
else:
    start_date, end_date = pd.to_datetime(date_range[0]).date(), pd.to_datetime(date_range[1]).date()
    if start_date > end_date:
        st.sidebar.error("La fecha inicial no puede ser mayor.")
        df_filtrado = df.iloc[0:0]
    else:
        df_filtrado = df[(df["Fecha"].dt.date >= start_date) & (df["Fecha"].dt.date <= end_date)]

def show_df_without_time(df_to_show):
    tmp = df_to_show.copy()
    if "Fecha" in tmp.columns:
        tmp["Fecha"] = tmp["Fecha"].dt.date
    st.dataframe(tmp)

# ================================
# 4) Dashboard General
# ================================
if menu == "🏠 Dashboard General":
    st.subheader("🏠 Dashboard General")

    if df_filtrado.empty:
        st.warning("No hay datos para el rango seleccionado.")
    else:
        col1, col2 = st.columns(2)

        # 1. Ventas por cliente (ejes invertidos)
        with col1:
            st.markdown("### 💰 Ventas por Cliente")
            df_cliente = df_filtrado.groupby("Cliente", as_index=False)["Total"].sum()

            chart = (
                alt.Chart(df_cliente)
                .mark_bar()
                .encode(
                    y=alt.Y("Cliente:N", sort="-x"),  # eje vertical nominal
                    x="Total:Q",                      # eje horizontal cuantitativo
                    tooltip=["Cliente", "Total"]
                )
            )
            st.altair_chart(chart, use_container_width=True)

        # 2. Productos más vendidos (rosado, ejes invertidos)
        with col2:
            st.markdown("### 📦 Productos más vendidos")
            df_prod = df_filtrado.groupby("Producto", as_index=False)["Cantidad"].sum()

            chart2 = (
                alt.Chart(df_prod)
                .mark_bar(color="#ff6fbf")   # rosado
                .encode(
                    y=alt.Y("Producto:N", sort="-x"),  # eje vertical nominal
                    x="Cantidad:Q",                     # eje horizontal cuantitativo
                    tooltip=["Producto", "Cantidad"]
                )
            )
            st.altair_chart(chart2, use_container_width=True)


# ================================
# 5) CLIENTES
# ================================
elif menu == "👥 Clientes":
    st.subheader("👥 Análisis por Cliente")
    clientes = sorted(df["Cliente"].dropna().unique())
    cliente_sel = st.selectbox("Selecciona un cliente", ["- Todos -"] + clientes)
    
    if df_filtrado.empty:
        st.warning("No hay datos.")
    else:
        df_c = df_filtrado if cliente_sel == "- Todos -" else df_filtrado[df_filtrado["Cliente"] == cliente_sel]
        st.metric("Total consumido", f"S/ {df_c['Total'].sum():.2f}")

        # Agrupar por Producto y sumar Total
        df_prod = df_c.groupby("Producto", as_index=False)["Total"].sum()

        chart = alt.Chart(df_prod).mark_bar(color="#80c683").encode(
            y=alt.Y("Producto:N", sort="-x"),  # categorías en Y
            x="Total:Q",                        # ahora valores en X = Total
            tooltip=["Producto", "Total"]
        )
        st.altair_chart(chart, use_container_width=True)

        st.markdown("### 📋 Detalle")
        show_df_without_time(df_c)

# ================================
# 6) PRODUCTOS (con 2 dropdown relacionados)
# ================================
elif menu == "📦 Productos":
    st.subheader("📦 Análisis por Producto")

    if df_filtrado.empty:
        st.warning("No hay datos.")
    else:
        # 🟢 Crear lista de categorías únicas de la pestaña filtrada
        categorias = sorted(df_filtrado["Categoría"].dropna().unique())
        categoria_sel = st.selectbox("Categoría", ["- Todas -"] + categorias)

        # Filtrar productos según la categoría seleccionada
        if categoria_sel == "- Todas -":
            df_categoria = df_filtrado
        else:
            df_categoria = df_filtrado[df_filtrado["Categoría"] == categoria_sel]

        # Dropdown de productos según la categoría seleccionada
        productos = sorted(df_categoria["Producto"].dropna().unique())
        producto_sel = st.selectbox("Producto", ["- Todos -"] + productos)

        # Filtrar según producto seleccionado
        if producto_sel == "- Todos -":
            df_p = df_categoria
        else:
            df_p = df_categoria[df_categoria["Producto"] == producto_sel]

        # Mostrar métricas
        st.metric("Total vendido", int(df_p["Cantidad"].sum()))

        # Gráfico de evolución de ventas
        chart = alt.Chart(df_p).mark_line(point=True, color="#8e59ff").encode(
            x=alt.X("Fecha:T", axis=alt.Axis(format="%Y-%m-%d")),
            y="Cantidad:Q",
            tooltip=["Fecha", "Cantidad"]
        )
        st.altair_chart(chart, use_container_width=True)

        # Tabla
        show_df_without_time(df_p)


# ================================
# 7) VENTAS
# ================================
elif menu == "🧾 Ventas":
    st.subheader("🧾 Lista de Ventas")
    show_df_without_time(df_filtrado)
