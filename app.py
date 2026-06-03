import streamlit as st
import pandas as pd
from datetime import datetime
from urllib.parse import quote
from io import BytesIO

st.set_page_config(
    page_title="itunginDong - Split Bill",
    page_icon="💸",
    layout="wide",
)

# =========================
# STYLE
# =========================
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.4rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }
    .subtitle {
        color: #666;
        margin-top: 0;
        margin-bottom: 1.2rem;
    }
    .card {
        border: 1px solid rgba(49, 51, 63, 0.15);
        border-radius: 18px;
        padding: 18px 20px;
        background: rgba(255,255,255,0.72);
        box-shadow: 0 4px 18px rgba(0,0,0,0.04);
        margin-bottom: 16px;
    }
    .receipt {
        border: 1px dashed #999;
        border-radius: 16px;
        padding: 20px;
        background: #fffdf7;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        color: #222;
        white-space: pre-wrap;
    }
    .success-pill {
        display: inline-block;
        padding: 6px 12px;
        border-radius: 999px;
        background: #e9fff2;
        color: #087b35;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .small-muted { color: #777; font-size: 0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# HELPERS
# =========================
def rupiah(value: float) -> str:
    try:
        value = float(value)
    except Exception:
        value = 0
    return f"Rp{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def clean_people(df: pd.DataFrame) -> list[str]:
    if df is None or df.empty or "Nama" not in df.columns:
        return []
    names = []
    for name in df["Nama"].fillna("").astype(str):
        name = name.strip()
        if name and name not in names:
            names.append(name)
    return names


def calculate_settlement(expenses: list[dict], people: list[str]):
    paid = {p: 0.0 for p in people}
    share = {p: 0.0 for p in people}
    detail_rows = []

    for exp in expenses:
        payer = exp["payer"]
        participants = exp["participants"]
        amount = float(exp["amount"])
        tax_percent = float(exp.get("tax_percent", 0) or 0)
        total = amount * (1 + tax_percent / 100)

        paid[payer] += total

        if exp["split_mode"] == "Sama rata":
            each = total / len(participants)
            for person in participants:
                share[person] += each
                detail_rows.append({
                    "Transaksi": exp["item"],
                    "Pembayar": payer,
                    "Orang": person,
                    "Porsi": each,
                })
        else:
            custom_shares = exp.get("custom_shares", {})
            custom_total = sum(float(custom_shares.get(p, 0) or 0) for p in participants)
            if custom_total <= 0:
                each = total / len(participants)
                for person in participants:
                    share[person] += each
                    detail_rows.append({"Transaksi": exp["item"], "Pembayar": payer, "Orang": person, "Porsi": each})
            else:
                # custom amount is treated as final nominal share; if not equal to total, normalize proportionally
                factor = total / custom_total
                for person in participants:
                    nominal = float(custom_shares.get(person, 0) or 0) * factor
                    share[person] += nominal
                    detail_rows.append({"Transaksi": exp["item"], "Pembayar": payer, "Orang": person, "Porsi": nominal})

    balance = {p: paid[p] - share[p] for p in people}

    debtors = sorted([(p, -b) for p, b in balance.items() if b < -0.5], key=lambda x: x[1], reverse=True)
    creditors = sorted([(p, b) for p, b in balance.items() if b > 0.5], key=lambda x: x[1], reverse=True)

    settlements = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor, debt = debtors[i]
        creditor, credit = creditors[j]
        pay_amount = min(debt, credit)
        if pay_amount > 0.5:
            settlements.append({"Dari": debtor, "Ke": creditor, "Nominal": round(pay_amount, 2)})
        debt -= pay_amount
        credit -= pay_amount
        debtors[i] = (debtor, debt)
        creditors[j] = (creditor, credit)
        if debt <= 0.5:
            i += 1
        if credit <= 0.5:
            j += 1

    summary = pd.DataFrame({
        "Nama": people,
        "Total Dibayarkan": [paid[p] for p in people],
        "Jatah Konsumsi/Barang": [share[p] for p in people],
        "Saldo Bersih": [balance[p] for p in people],
    })

    details = pd.DataFrame(detail_rows)
    settlements_df = pd.DataFrame(settlements, columns=["Dari", "Ke", "Nominal"])
    return summary, details, settlements_df


def make_receipt(trip_name: str, people: list[str], expenses: list[dict], settlements_df: pd.DataFrame, summary: pd.DataFrame) -> str:
    now = datetime.now().strftime("%d %B %Y, %H:%M")
    lines = []
    lines.append("================================")
    lines.append("          itunginDong")
    lines.append("      Bukti Split Utang")
    lines.append("================================")
    lines.append(f"Acara    : {trip_name or '-'}")
    lines.append(f"Tanggal  : {now}")
    lines.append(f"Anggota  : {', '.join(people)}")
    lines.append("--------------------------------")
    lines.append("RINCIAN TRANSAKSI")
    for idx, exp in enumerate(expenses, start=1):
        total = float(exp["amount"]) * (1 + float(exp.get("tax_percent", 0) or 0) / 100)
        tax_text = f" + tax {exp.get('tax_percent', 0)}%" if float(exp.get("tax_percent", 0) or 0) > 0 else ""
        lines.append(f"{idx}. {exp['item']}")
        lines.append(f"   Dibayar oleh : {exp['payer']}")
        lines.append(f"   Peserta      : {', '.join(exp['participants'])}")
        lines.append(f"   Total        : {rupiah(total)}{tax_text}")
    lines.append("--------------------------------")
    lines.append("YANG PERLU DIBAYAR")
    if settlements_df.empty:
        lines.append("Semua sudah impas. Tidak ada yang perlu transfer.")
    else:
        for _, row in settlements_df.iterrows():
            lines.append(f"- {row['Dari']} bayar ke {row['Ke']}: {rupiah(row['Nominal'])}")
    lines.append("--------------------------------")
    lines.append("SALDO BERSIH")
    for _, row in summary.iterrows():
        status = "menerima" if row["Saldo Bersih"] > 0.5 else "membayar" if row["Saldo Bersih"] < -0.5 else "impas"
        lines.append(f"- {row['Nama']}: {rupiah(abs(row['Saldo Bersih']))} ({status})")
    lines.append("================================")
    lines.append("Generated by itunginDong 💸")
    return "\n".join(lines)


def init_state():
    if "people_df" not in st.session_state:
        st.session_state.people_df = pd.DataFrame({"Nama": ["siti", "ade", "azza", "asa"]})
    if "expenses" not in st.session_state:
        st.session_state.expenses = []


init_state()

# =========================
# HEADER
# =========================
st.markdown('<div class="main-title">💸 itunginDong</div>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Aplikasi split bill utang-piutang antar teman. Cocok buat jalan-jalan, makan bareng, patungan kado, atau titipan barang.</p>', unsafe_allow_html=True)

left, right = st.columns([1.05, 1.4], gap="large")

with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("1. Nama acara")
    trip_name = st.text_input("Contoh: Trip Jogja", value="Trip Jogja")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("2. Daftar orang")
    st.caption("Tambah nama dengan klik baris kosong di bawah tabel, atau klik tombol + pada tabel.")
    people_editor = st.data_editor(
        st.session_state.people_df,
        num_rows="dynamic",
        use_container_width=True,
        key="people_editor",
        column_config={"Nama": st.column_config.TextColumn("Nama", required=False, help="Masukkan nama teman")},
    )
    st.session_state.people_df = people_editor
    people = clean_people(people_editor)
    if people:
        st.success(f"Anggota aktif: {', '.join(people)}")
    else:
        st.warning("Isi minimal 2 nama dulu ya.")
    st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("3. Tambah transaksi")

    if len(people) < 2:
        st.info("Tambahkan minimal 2 orang untuk mulai input transaksi.")
    else:
        with st.form("expense_form", clear_on_submit=False):
            c1, c2 = st.columns([1.2, 1])
            with c1:
                item = st.text_input("Nama transaksi", placeholder="Contoh: Es dawet, GoCar, Gelang")
                payer = st.selectbox("Siapa yang bayarin?", people)
                participants = st.multiselect(
                    "Siapa saja yang ikut dibayarin / dapat barang?",
                    people,
                    default=people,
                    help="Untuk kasus titipan, masukkan juga orang yang nitip ke daftar orang, lalu centang namanya di sini.",
                )
            with c2:
                amount = st.number_input("Harga sebelum tax / total barang", min_value=0.0, step=1000.0, format="%.2f")
                tax_percent = st.number_input("Tax / pajak (%) - boleh kosong/0", min_value=0.0, step=1.0, format="%.2f")
                split_mode = st.radio("Metode split", ["Sama rata", "Custom nominal"], horizontal=True)

            custom_shares = {}
            if split_mode == "Custom nominal" and participants:
                st.caption("Isi nominal porsi masing-masing. Kalau totalnya tidak sama dengan total transaksi, sistem akan menyesuaikan secara proporsional.")
                custom_df = pd.DataFrame({"Nama": participants, "Nominal Porsi": [0.0] * len(participants)})
                edited_custom = st.data_editor(
                    custom_df,
                    use_container_width=True,
                    hide_index=True,
                    disabled=["Nama"],
                    key="custom_split_editor",
                    column_config={
                        "Nominal Porsi": st.column_config.NumberColumn("Nominal Porsi", min_value=0.0, step=1000.0, format="%.2f")
                    },
                )
                custom_shares = dict(zip(edited_custom["Nama"], edited_custom["Nominal Porsi"]))

            submitted = st.form_submit_button("➕ Tambahkan transaksi", use_container_width=True)
            if submitted:
                if not item.strip():
                    st.error("Nama transaksi belum diisi.")
                elif amount <= 0:
                    st.error("Nominal harus lebih dari 0.")
                elif not participants:
                    st.error("Pilih minimal 1 orang yang ikut dibayarin.")
                elif payer not in people:
                    st.error("Nama pembayar belum ada di daftar orang.")
                else:
                    st.session_state.expenses.append({
                        "item": item.strip(),
                        "payer": payer,
                        "participants": participants,
                        "amount": float(amount),
                        "tax_percent": float(tax_percent),
                        "split_mode": split_mode,
                        "custom_shares": custom_shares,
                    })
                    st.success("Transaksi berhasil ditambahkan.")
    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# EXPENSE LIST
# =========================
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("4. Daftar transaksi")

if not st.session_state.expenses:
    st.info("Belum ada transaksi. Tambahkan transaksi dulu di form atas.")
else:
    expense_rows = []
    for idx, exp in enumerate(st.session_state.expenses, start=1):
        total = float(exp["amount"]) * (1 + float(exp.get("tax_percent", 0) or 0) / 100)
        expense_rows.append({
            "No": idx,
            "Transaksi": exp["item"],
            "Pembayar": exp["payer"],
            "Peserta Split": ", ".join(exp["participants"]),
            "Tax (%)": exp.get("tax_percent", 0),
            "Total Final": rupiah(total),
            "Metode": exp["split_mode"],
        })
    st.dataframe(pd.DataFrame(expense_rows), use_container_width=True, hide_index=True)

    c_reset, c_delete = st.columns([1, 1])
    with c_reset:
        if st.button("🗑️ Hapus semua transaksi", use_container_width=True):
            st.session_state.expenses = []
            st.rerun()
    with c_delete:
        delete_no = st.number_input("Hapus transaksi nomor", min_value=1, max_value=len(st.session_state.expenses), step=1)
        if st.button("Hapus nomor ini", use_container_width=True):
            st.session_state.expenses.pop(delete_no - 1)
            st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

# =========================
# RESULT
# =========================
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("5. Hasil split & struk")

people = clean_people(st.session_state.people_df)
if len(people) < 2 or not st.session_state.expenses:
    st.info("Hasil akan muncul setelah daftar orang dan transaksi diisi.")
else:
    # Validate all names still exist after editing people list
    valid = True
    missing_names = set()
    for exp in st.session_state.expenses:
        if exp["payer"] not in people:
            missing_names.add(exp["payer"])
        for p in exp["participants"]:
            if p not in people:
                missing_names.add(p)
    if missing_names:
        valid = False
        st.error(f"Ada nama di transaksi yang sudah tidak ada di daftar orang: {', '.join(missing_names)}. Tambahkan lagi namanya atau hapus transaksi terkait.")

    if valid:
        summary, details, settlements_df = calculate_settlement(st.session_state.expenses, people)

        s1, s2 = st.columns([1.1, 1])
        with s1:
            st.markdown("**Ringkasan per orang**")
            display_summary = summary.copy()
            for col in ["Total Dibayarkan", "Jatah Konsumsi/Barang", "Saldo Bersih"]:
                display_summary[col] = display_summary[col].apply(rupiah)
            st.dataframe(display_summary, use_container_width=True, hide_index=True)

        with s2:
            st.markdown("**Transfer yang disarankan**")
            if settlements_df.empty:
                st.success("Semua sudah impas. Tidak ada yang perlu transfer.")
            else:
                show_settlement = settlements_df.copy()
                show_settlement["Nominal"] = show_settlement["Nominal"].apply(rupiah)
                st.dataframe(show_settlement, use_container_width=True, hide_index=True)

        receipt = make_receipt(trip_name, people, st.session_state.expenses, settlements_df, summary)
        st.markdown('<div class="receipt">' + receipt.replace("\n", "<br>") + '</div>', unsafe_allow_html=True)

        st.divider()
        d1, d2 = st.columns([1, 1])
        with d1:
            st.download_button(
                "⬇️ Download struk (.txt)",
                data=receipt.encode("utf-8"),
                file_name=f"struk_itunginDong_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain",
                use_container_width=True,
            )
        with d2:
            whatsapp_text = quote(receipt)
            st.link_button("📲 Share ke WhatsApp", f"https://wa.me/?text={whatsapp_text}", use_container_width=True)

st.markdown("</div>", unsafe_allow_html=True)

# =========================
# DEMO BUTTON
# =========================
with st.expander("✨ Isi contoh otomatis: Trip Jogja"):
    st.write("Contoh: siti bayarin es dawet, azza bayarin GoCar, ade bayarin gelang termasuk asa yang nitip.")
    if st.button("Pakai data contoh"):
        st.session_state.people_df = pd.DataFrame({"Nama": ["siti", "ade", "azza", "asa"]})
        st.session_state.expenses = [
            {
                "item": "Es dawet",
                "payer": "siti",
                "participants": ["siti", "ade", "azza"],
                "amount": 24000.0,
                "tax_percent": 10.0,
                "split_mode": "Sama rata",
                "custom_shares": {},
            },
            {
                "item": "GoCar",
                "payer": "azza",
                "participants": ["siti", "ade", "azza"],
                "amount": 12000.0,
                "tax_percent": 0.0,
                "split_mode": "Sama rata",
                "custom_shares": {},
            },
            {
                "item": "Gelang titipan",
                "payer": "ade",
                "participants": ["siti", "ade", "azza", "asa"],
                "amount": 80000.0,
                "tax_percent": 0.0,
                "split_mode": "Sama rata",
                "custom_shares": {},
            },
        ]
        st.rerun()

st.caption("Tips: untuk kasus ada orang yang nitip tapi tidak ikut jalan, tetap masukkan namanya di daftar orang lalu centang hanya pada transaksi titipannya.")
