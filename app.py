import streamlit as st
import pandas as pd
from datetime import datetime
from urllib.parse import quote

st.set_page_config(
    page_title="itunginDong - Split Bill",
    page_icon="💸",
    layout="centered",
)

# =========================
# STYLE
# =========================
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.5rem;
        font-weight: 850;
        margin-bottom: 0.2rem;
    }
    .subtitle {
        color: #666;
        margin-top: 0;
        margin-bottom: 1.4rem;
        line-height: 1.5;
    }
    .card {
        border: 1px solid rgba(49, 51, 63, 0.14);
        border-radius: 18px;
        padding: 18px 20px;
        background: rgba(255,255,255,0.72);
        box-shadow: 0 4px 18px rgba(0,0,0,0.04);
        margin-bottom: 18px;
    }
    .transaction-card {
        border: 1px solid rgba(49, 51, 63, 0.12);
        border-radius: 14px;
        padding: 12px 14px;
        margin-bottom: 10px;
        background: rgba(250,250,250,0.75);
    }
    .transaction-title {
        font-weight: 750;
        font-size: 1rem;
        margin-bottom: 3px;
    }
    .small-muted {
        color: #777;
        font-size: 0.88rem;
        line-height: 1.45;
    }
    .receipt {
        border: 1px dashed #999;
        border-radius: 16px;
        padding: 20px;
        background: #fffdf7;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        color: #222;
        white-space: pre-wrap;
        overflow-wrap: break-word;
    }
    div[data-testid="stVerticalBlock"] > div:has(.card) {
        width: 100%;
    }
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


def calculate_total(amount: float, tax_percent: float) -> float:
    return float(amount) * (1 + float(tax_percent or 0) / 100)


def calculate_settlement(expenses: list[dict], people: list[str]):
    paid = {p: 0.0 for p in people}
    share = {p: 0.0 for p in people}
    detail_rows = []

    for exp in expenses:
        payer = exp["payer"]
        participants = exp["participants"]
        total = calculate_total(exp["amount"], exp.get("tax_percent", 0))

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
            for person in participants:
                nominal = float(custom_shares.get(person, 0) or 0)
                share[person] += nominal
                detail_rows.append({
                    "Transaksi": exp["item"],
                    "Pembayar": payer,
                    "Orang": person,
                    "Porsi": nominal,
                })

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
        total = calculate_total(exp["amount"], exp.get("tax_percent", 0))
        tax_value = float(exp.get("tax_percent", 0) or 0)
        tax_text = f" + tax {tax_value:g}%" if tax_value > 0 else ""
        lines.append(f"{idx}. {exp['item']}")
        lines.append(f"   Dibayar oleh : {exp['payer']}")
        lines.append(f"   Nama      : {', '.join(exp['participants'])}")
        lines.append(f"   Total        : {rupiah(total)}{tax_text}")
        lines.append(f"   Metode       : {exp['split_mode']}")
        if exp["split_mode"] == "Custom nominal":
            for person in exp["participants"]:
                lines.append(f"      - {person}: {rupiah(exp.get('custom_shares', {}).get(person, 0))}")

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
    if "edit_index" not in st.session_state:
        st.session_state.edit_index = None


def cancel_edit():
    st.session_state.edit_index = None


init_state()

# =========================
# HEADER
# =========================
st.markdown('<div class="main-title">💸 itunginDong</div>', unsafe_allow_html=True)
st.markdown(
    '<p class="subtitle">Aplikasi split bill utang-piutang antar teman. Cocok buat jalan-jalan, makan bareng, patungan kado, atau titipan barang.</p>',
    unsafe_allow_html=True,
)

# =========================
# STEP 1
# =========================
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("1. Nama acara")
trip_name = st.text_input("Contoh: Trip Jogja", value="Trip Jogja")
st.markdown("</div>", unsafe_allow_html=True)

# =========================
# STEP 2
# =========================
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

# =========================
# STEP 3 - FORM
# =========================
st.markdown('<div class="card">', unsafe_allow_html=True)
edit_index = st.session_state.edit_index
is_editing = edit_index is not None and 0 <= edit_index < len(st.session_state.expenses)
edit_exp = st.session_state.expenses[edit_index] if is_editing else None

st.subheader("3. Tambah transaksi" if not is_editing else f"3. Edit transaksi #{edit_index + 1}")

if len(people) < 2:
    st.info("Tambahkan minimal 2 orang untuk mulai input transaksi.")
else:
    default_item = edit_exp["item"] if is_editing else ""
    default_payer = edit_exp["payer"] if is_editing and edit_exp["payer"] in people else people[0]
    default_participants = [p for p in (edit_exp["participants"] if is_editing else people) if p in people]
    default_amount = float(edit_exp["amount"]) if is_editing else 0.0
    default_tax = float(edit_exp.get("tax_percent", 0)) if is_editing else 0.0
    default_split = edit_exp["split_mode"] if is_editing else "Sama rata"

    with st.form("expense_form", clear_on_submit=False):
        item = st.text_input("Nama transaksi", value=default_item, placeholder="Contoh: Es dawet, GoCar, Gelang")
        payer = st.selectbox("Siapa yang bayarin?", people, index=people.index(default_payer))
        participants = st.multiselect(
            "Siapa saja yang ikut dibayarin / dapat barang?",
            people,
            default=default_participants,
            help="Untuk kasus titipan, masukkan juga orang yang nitip ke daftar orang, lalu centang namanya di sini.",
        )
        amount = st.number_input(
            "Harga sebelum tax / total barang",
            min_value=0.0,
            step=1000.0,
            format="%.2f",
            value=default_amount,
        )
        tax_percent = st.number_input(
            "Tax / pajak (%) - boleh kosong/0",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            value=default_tax,
        )
        split_mode = st.radio(
            "Metode split",
            ["Sama rata", "Custom nominal"],
            index=["Sama rata", "Custom nominal"].index(default_split),
            horizontal=False,
        )

        custom_shares = {}
        total_final = calculate_total(amount, tax_percent)

        if split_mode == "Custom nominal" and participants:
            st.info(
                f"Total final transaksi ini: {rupiah(total_final)}. Isi nominal porsi tiap Nama sampai totalnya sama."
            )
            old_custom = edit_exp.get("custom_shares", {}) if is_editing else {}
            custom_df = pd.DataFrame({
                "Nama": participants,
                "Nominal Porsi": [float(old_custom.get(p, 0) or 0) for p in participants],
            })
            edited_custom = st.data_editor(
                custom_df,
                use_container_width=True,
                hide_index=True,
                disabled=["Nama"],
                key=f"custom_split_editor_{edit_index if is_editing else 'new'}",
                column_config={
                    "Nominal Porsi": st.column_config.NumberColumn(
                        "Nominal Porsi", min_value=0.0, step=1000.0, format="%.2f"
                    )
                },
            )
            custom_shares = dict(zip(edited_custom["Nama"], edited_custom["Nominal Porsi"]))
            custom_total = sum(float(v or 0) for v in custom_shares.values())
            selisih = total_final - custom_total
            st.caption(f"Total custom: {rupiah(custom_total)} | Selisih: {rupiah(selisih)}")

        submit_label = "💾 Simpan perubahan" if is_editing else "➕ Tambahkan transaksi"
        submitted = st.form_submit_button(submit_label, use_container_width=True)

        if submitted:
            if not item.strip():
                st.error("Nama transaksi belum diisi.")
            elif amount <= 0:
                st.error("Nominal harus lebih dari 0.")
            elif not participants:
                st.error("Pilih minimal 1 orang yang ikut dibayarin.")
            elif payer not in people:
                st.error("Nama pembayar belum ada di daftar orang.")
            elif split_mode == "Custom nominal" and abs(sum(float(v or 0) for v in custom_shares.values()) - total_final) > 1:
                st.error("Total custom nominal harus sama dengan total final transaksi. Cek lagi nominal per orangnya ya.")
            else:
                new_expense = {
                    "item": item.strip(),
                    "payer": payer,
                    "participants": participants,
                    "amount": float(amount),
                    "tax_percent": float(tax_percent),
                    "split_mode": split_mode,
                    "custom_shares": custom_shares if split_mode == "Custom nominal" else {},
                }
                if is_editing:
                    st.session_state.expenses[edit_index] = new_expense
                    st.session_state.edit_index = None
                    st.success("Transaksi berhasil diperbarui.")
                else:
                    st.session_state.expenses.append(new_expense)
                    st.success("Transaksi berhasil ditambahkan.")
                st.rerun()

    if is_editing:
        if st.button("Batal edit", use_container_width=True):
            cancel_edit()
            st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

# =========================
# STEP 4 - EXPENSE LIST
# =========================
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("4. Daftar transaksi")

if not st.session_state.expenses:
    st.info("Belum ada transaksi. Tambahkan transaksi dulu di form atas.")
else:
    for idx, exp in enumerate(st.session_state.expenses):
        total = calculate_total(exp["amount"], exp.get("tax_percent", 0))
        st.markdown('<div class="transaction-card">', unsafe_allow_html=True)
        action_col, edit_col, delete_col = st.columns([8, 1, 1])
        with action_col:
            st.markdown(f'<div class="transaction-title">{idx + 1}. {exp["item"]}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="small-muted">Dibayar oleh <b>{exp["payer"]}</b> • Nama: {", ".join(exp["participants"])}<br>'
                f'Total final: <b>{rupiah(total)}</b> • Metode: {exp["split_mode"]}</div>',
                unsafe_allow_html=True,
            )
        with edit_col:
            if st.button("✏️", key=f"edit_{idx}", help="Edit transaksi"):
                st.session_state.edit_index = idx
                st.rerun()
        with delete_col:
            if st.button("🗑️", key=f"delete_{idx}", help="Hapus transaksi"):
                st.session_state.expenses.pop(idx)
                if st.session_state.edit_index == idx:
                    st.session_state.edit_index = None
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    if st.button("🗑️ Hapus semua transaksi", use_container_width=True):
        st.session_state.expenses = []
        st.session_state.edit_index = None
        st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

# =========================
# STEP 5 - RESULT
# =========================
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("5. Hasil split & struk")

people = clean_people(st.session_state.people_df)
if len(people) < 2 or not st.session_state.expenses:
    st.info("Hasil akan muncul setelah daftar orang dan transaksi diisi.")
else:
    missing_names = set()
    for exp in st.session_state.expenses:
        if exp["payer"] not in people:
            missing_names.add(exp["payer"])
        for p in exp["participants"]:
            if p not in people:
                missing_names.add(p)

    if missing_names:
        st.error(
            f"Ada nama di transaksi yang sudah tidak ada di daftar orang: {', '.join(missing_names)}. "
            "Tambahkan lagi namanya atau edit/hapus transaksi terkait."
        )
    else:
        summary, details, settlements_df = calculate_settlement(st.session_state.expenses, people)

        st.markdown("**Ringkasan per orang**")
        display_summary = summary.copy()
        for col in ["Total Dibayarkan", "Jatah Konsumsi/Barang", "Saldo Bersih"]:
            display_summary[col] = display_summary[col].apply(rupiah)
        st.dataframe(display_summary, use_container_width=True, hide_index=True)

        st.markdown("**Transfer yang disarankan**")
        if settlements_df.empty:
            st.success("Semua sudah impas. Tidak ada yang perlu transfer.")
        else:
            show_settlement = settlements_df.copy()
            show_settlement["Nominal"] = show_settlement["Nominal"].apply(rupiah)
            st.dataframe(show_settlement, use_container_width=True, hide_index=True)

        receipt = make_receipt(trip_name, people, st.session_state.expenses, settlements_df, summary)
        st.markdown('<div class="receipt">' + receipt.replace("\n", "<br>") + '</div>', unsafe_allow_html=True)

        st.download_button(
            "⬇️ Download struk (.txt)",
            data=receipt.encode("utf-8"),
            file_name=f"struk_itunginDong_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
        )
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
                "split_mode": "Custom nominal",
                "custom_shares": {
                    "siti": 20000.0,
                    "ade": 20000.0,
                    "azza": 20000.0,
                    "asa": 20000.0,
                },
            },
        ]
        st.session_state.edit_index = None
        st.rerun()