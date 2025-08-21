import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# === Configuration de la page ===
st.set_page_config(page_title="Reboot Dashboard for Tag V3(installed with V2)", layout="wide")

# === Chargement des données ===
df = pd.read_csv("Device_Status.csv")
stats = pd.read_csv("Device_Statistic.csv")

# === Prétraitement ===
stats["BatteryLevelMax"] = stats["BatteryLevelMax"] * 0.064
stats["BatteryLevelMin"] = stats["BatteryLevelMin"] * 0.064

df = df.dropna(subset=['LogDate'])
df = df[df['LogDate'] != '']
df['LogDate'] = pd.to_datetime(df['LogDate'], dayfirst=True, errors='coerce')
stats['LogDate'] = pd.to_datetime(stats['LogDate'], dayfirst=True, errors='coerce')
df['SerialNumber'] = df['SerialNumber'].astype(str)
stats['SerialNumber'] = stats['SerialNumber'].astype(str)

df = df[~df['TagId'].isin([0, 4294967295, None, np.nan])]

df.sort_values(by=['SerialNumber', 'LogDate'], inplace=True)
df['DeviceID'] = df['SerialNumber']
df['PowerUpCounter_Diff'] = df.groupby('DeviceID')['PowerUpCounter'].diff()
df['RebootCount'] = df['PowerUpCounter_Diff'].apply(lambda x: int(x) if pd.notnull(x) and x > 0 else 0)

powerup_mapping = {
    0: 'TBD', 1: 'COLD', 2: 'WATCHDOG', 3: 'FORCED_SANITY',
    4: 'COMMUNICATION_EXPIRED', 5: 'LOCAL_REBOOT', 6: 'REMOTE_REBOOT',
    7: 'UPGRADE_REQUEST', 8: 'HARDWARE', 9: 'RESET_PIN',
    10: 'PWR_BOR', 11: 'LOW_PWR', 128: 'HARDWARE_NONE'
}

# === Construire la table des reboot ===
reboot_rows = []
for _, row in df[df['RebootCount'] > 0].iterrows():
    reason = powerup_mapping.get(row['PowerUpReason'], 'HARDWARE_UNKNOWN')
    for _ in range(int(row['RebootCount'])):
        reboot_rows.append({
            'DeviceID': row['DeviceID'],
            'PowerUpReason': reason,
            'TagId': row['TagId'],
            'UId': row['UId']
        })

reboot_df = pd.DataFrame(reboot_rows)

# === Exclure le premier log de chaque SerialNumber ===
first_logs = stats.sort_values('LogDate').groupby('SerialNumber').first().reset_index()
first_logs = first_logs[['SerialNumber', 'LogDate']]
stats = stats.merge(first_logs, on='SerialNumber', how='left', suffixes=('', '_First'))
stats = stats[stats['LogDate'] != stats['LogDate_First']]
stats.drop(columns=['LogDate_First'], inplace=True)

# === Calcul basé sur le DERNIER log ===
battery_df = stats.sort_values('LogDate', ascending=False).groupby('SerialNumber').first().reset_index()
battery_df = battery_df[['SerialNumber', 'BatteryLevelMin', 'BatteryLevelMax']]

# === Interface Streamlit ===
st.title("Reboot Dashboard Interactive")

# === Reboot Reason Chart ===
filt = reboot_df.copy()
reason_counts = filt['PowerUpReason'].value_counts().reset_index()
reason_counts.columns = ['PowerUpReason', 'Count']
if not reason_counts.empty:
    reason_counts['Percentage'] = (reason_counts['Count'] / reason_counts['Count'].sum()) * 100

    fig = px.bar(
        reason_counts,
        x="PowerUpReason",
        y="Percentage",
        hover_data={"Count": True, "Percentage": ':.2f'},
        labels={"Percentage": "%"},
        title="Reboot Causes (%)",
        color="PowerUpReason",
        color_discrete_sequence=px.colors.qualitative.Set3
    )
    fig.update_traces(texttemplate='%{y:.2f}%', textposition='outside', textfont_color='black')
    fig.update_layout(xaxis_title="PowerUp Reason", yaxis_title="Percentage")
    st.plotly_chart(fig, use_container_width=True)

    selected_reason = st.selectbox("Select Reboot Cause to View Devices", reason_counts['PowerUpReason'].tolist())
    selection = filt[filt['PowerUpReason'] == selected_reason][['DeviceID', 'TagId', 'UId']].drop_duplicates()
    st.markdown(f"**Number of selected devices: {selection['DeviceID'].nunique()}**")
    st.dataframe(selection)

    csv = selection.to_csv(index=False).encode('utf-8')
    st.download_button("📅 PowerUpReason Export CSV", data=csv, file_name="selected_devices.csv", mime='text/csv')
else:
    st.info("No data for selected filters.")

# === Battery Chart (moyennes globales) ===
batt_filt = battery_df.copy()
if not batt_filt.empty:
    avg_min = batt_filt["BatteryLevelMin"].mean()
    avg_max = batt_filt["BatteryLevelMax"].mean()

    batt_df = pd.DataFrame({
        "Metric": ["BatteryLevelMin", "BatteryLevelMax"],
        "Average": [avg_min, avg_max],
    })

    fig_batt = px.bar(
        batt_df,
        x="Metric",
        y="Average",
        color="Metric",
        color_discrete_map={
            "BatteryLevelMin": "#1f77b4",
            "BatteryLevelMax": "#ff7f0e"
        },
        title="Battery Level (Average)",
        labels={"Metric": "Battery Level", "Average": "Average in Volts"}
    )
    st.plotly_chart(fig_batt, use_container_width=True)
else:
    st.info("No battery data available.")

# === Batterie faible (< 3.1V) ===
low_battery_df = battery_df[battery_df['BatteryLevelMin'] < 3.1].copy()
st.markdown("### ⚠️ Devices avec une batterie faible (< 3.1 V)")
st.markdown(f"Nombre total de devices concernés : **{low_battery_df.shape[0]}**")

if not low_battery_df.empty:
    st.dataframe(low_battery_df[['SerialNumber', 'BatteryLevelMin', 'BatteryLevelMax']])

    fig_low_batt = px.histogram(
        low_battery_df,
        x="BatteryLevelMin",
        nbins=20,
        title="Distribution des BatteryLevelMin < 3.1V",
        labels={"BatteryLevelMin": "Battery Level Min (V)"},
        color_discrete_sequence=px.colors.qualitative.Set2
    )
    fig_low_batt.update_layout(bargap=0.1)
    st.plotly_chart(fig_low_batt, use_container_width=True)

    csv_low_batt = low_battery_df.to_csv(index=False).encode('utf-8')
    st.download_button("📅 Low Battery TagV3 Export (CSV)", data=csv_low_batt, file_name="low_battery_devices.csv", mime='text/csv')
else:
    st.success("✅ Aucun device avec une batterie inférieure à 3.1 V.")
