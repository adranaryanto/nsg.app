from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file,
    send_from_directory
)

import json
import os
import csv
import requests
import base64
import html
import hashlib

from werkzeug.utils import secure_filename

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer
)


# ============================================================
# GOOGLE APPS SCRIPT - BOOKING / PEMINJAMAN
# ============================================================
# URL TERBARU YANG DIBERIKAN
# ============================================================

GOOGLE_APPS_SCRIPT_BOOKING_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxakOtSCMq6fAstFRgUHWmse8Fu3qJjo9o4A-XpsusuzoV_BCz25-660j0DYEH7SboF"
    "/exec"
)


# ============================================================
# GOOGLE APPS SCRIPT - UPLOAD GOOGLE DRIVE
# ============================================================

GOOGLE_APPS_SCRIPT_UPLOAD_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxpUX3nhT-c-SwYY7TvWev_9ej81E4jXgiZb75A0Iz8Agvc_llkyZfYfJgCzgt_pmXb"
    "/exec"
)


# ============================================================
# GOOGLE DRIVE UTAMA
# ============================================================

GOOGLE_DRIVE_URL = (
    "https://drive.google.com/drive/folders/"
    "1KySCCNFRx-9dn6cetV-gxhKfiuf8Cz-4?usp=drive_link"
)


# ============================================================
# GOOGLE SPREADSHEET BOOKING
# ============================================================

GOOGLE_BOOKING_SPREADSHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1FkxTNoUveHNvWseFoFZJA-xxNS3PgX1dSv7LjLx1UvU"
    "/edit?usp=sharing"
)

GOOGLE_BOOKING_SPREADSHEET_ID = (
    "1FkxTNoUveHNvWseFoFZJA-xxNS3PgX1dSv7LjLx1UvU"
)


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.secret_key = "logbook-nsg-secret-key"


# ============================================================
# LOGIN
# ============================================================

USERNAME = "admin"
PASSWORD = "1234"


# ============================================================
# FILE DAN FOLDER
# ============================================================

MEMBER_FILE = "members.json"

DATA_FOLDER = "data"

UPLOAD_FOLDER = "uploads"

PDF_FOLDER = "pdf"

# ============================================================
# DATA BOOKING UNTUK KALENDER
# ============================================================

BOOKING_DATA_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    DATA_FOLDER,
    "bookings.json"
)


# ============================================================
# BUAT FOLDER
# ============================================================

os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)


# ============================================================
# FORMAT FILE YANG DIIZINKAN
# ============================================================

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "csv"
}


def booking_id(booking):
    """
    ID stabil untuk setiap booking.
    Booking lama yang belum memiliki field 'id' tetap bisa
    dihapus karena ID dihitung dari isi datanya.
    """
    existing = str(booking.get("id", "")).strip()
    if existing:
        return existing

    # Booking lama tetap menggunakan struktur/ID lama.
    # Booking baru dengan rentang tanggal ikut memasukkan rentang
    # tanggal agar ID tetap unik.
    source = {
        "nama": str(booking.get("nama", "")).strip(),
        "nomor_telepon": str(booking.get("nomor_telepon", "")).strip(),
        "alat": str(booking.get("alat", "")).strip(),
        "tanggal": str(booking.get("tanggal_mulai") or booking.get("tanggal") or "").strip(),
        "tanggal_mulai": str(
            booking.get("tanggal_mulai")
            or booking.get("tanggal")
            or ""
        ).strip(),
        "tanggal_selesai": str(
            booking.get("tanggal_selesai")
            or booking.get("tanggal_mulai")
            or booking.get("tanggal")
            or ""
        ).strip(),
        "jam_mulai": str(booking.get("jam_mulai", "")).strip(),
        "jam_selesai": str(booking.get("jam_selesai", "")).strip(),
        "keperluan": str(booking.get("keperluan", "")).strip(),
        "catatan": str(booking.get("catatan", "")).strip(),
    }

    tanggal_mulai = str(
        booking.get("tanggal_mulai", "")
    ).strip()
    tanggal_selesai = str(
        booking.get("tanggal_selesai", "")
    ).strip()

    if tanggal_mulai or tanggal_selesai:
        source["tanggal_mulai"] = tanggal_mulai
        source["tanggal_selesai"] = tanggal_selesai

    raw = json.dumps(
        source,
        ensure_ascii=False,
        sort_keys=True
    )

    return "bk_" + hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]


def normalize_booking(booking):
    """Menjamin setiap booking yang dikirim ke kalender memiliki ID."""
    if not isinstance(booking, dict):
        return None

    item = dict(booking)

    # Kompatibilitas booking lama: jika hanya memiliki "tanggal",
    # anggap sebagai booking 1 hari.
    tanggal_legacy = str(item.get("tanggal", "")).strip()
    tanggal_mulai = str(item.get("tanggal_mulai", "")).strip()
    tanggal_selesai = str(item.get("tanggal_selesai", "")).strip()

    if not tanggal_mulai:
        tanggal_mulai = tanggal_legacy

    if not tanggal_selesai:
        tanggal_selesai = tanggal_mulai or tanggal_legacy

    item["tanggal_mulai"] = tanggal_mulai
    item["tanggal_selesai"] = tanggal_selesai

    # Field "tanggal" tetap dipertahankan untuk kompatibilitas lama
    # dan selalu berarti tanggal mulai.
    if not tanggal_legacy and tanggal_mulai:
        item["tanggal"] = tanggal_mulai

    item["id"] = booking_id(item)
    return item


def load_bookings():
    """Membaca seluruh data peminjaman yang menjadi sumber kalender."""

    try:
        if not os.path.exists(BOOKING_DATA_FILE):
            return []

        with open(
            BOOKING_DATA_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        if not isinstance(data, list):
            return []

        result = []

        for item in data:
            normalized = normalize_booking(item)

            if normalized:
                result.append(normalized)

        return result

    except Exception as e:
        print("Gagal membaca bookings.json:", e)
        return []


def write_bookings(bookings):
    """
    Menulis seluruh booking secara atomik.
    Dipakai untuk tambah maupun hapus booking.
    """

    os.makedirs(
        os.path.dirname(BOOKING_DATA_FILE),
        exist_ok=True
    )

    temp_file = BOOKING_DATA_FILE + ".tmp"

    with open(
        temp_file,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            bookings,
            file,
            ensure_ascii=False,
            indent=2
        )

    os.replace(
        temp_file,
        BOOKING_DATA_FILE
    )


def save_booking_for_calendar(booking):
    """
    Menyimpan HASIL INPUT FORM secara langsung ke bookings.json.

    Google Spreadsheet tidak digunakan sebagai sumber kalender.
    """

    # Simpan seluruh informasi rentang tanggal + waktu.
    # Ini penting karena kalender menggunakan tanggal_mulai dan
    # tanggal_selesai untuk menampilkan booking pada SETIAP hari
    # yang termasuk dalam rentang peminjaman.
    tanggal_mulai = str(
        booking.get("tanggal_mulai")
        or booking.get("tanggal")
        or ""
    ).strip()

    tanggal_selesai = str(
        booking.get("tanggal_selesai")
        or tanggal_mulai
        or booking.get("tanggal")
        or ""
    ).strip()

    booking_copy = {
        "id": booking_id(booking),
        "nama": str(booking.get("nama", "")).strip(),
        "nomor_telepon": str(booking.get("nomor_telepon", "")).strip(),
        "alat": str(booking.get("alat", "")).strip(),

        # "tanggal" tetap dipertahankan sebagai alias tanggal mulai.
        "tanggal": tanggal_mulai,
        "tanggal_mulai": tanggal_mulai,
        "tanggal_selesai": tanggal_selesai,

        "jam_mulai": str(booking.get("jam_mulai", "")).strip(),
        "jam_selesai": str(booking.get("jam_selesai", "")).strip(),
        "keperluan": str(booking.get("keperluan", "")).strip(),
        "catatan": str(booking.get("catatan", "")).strip()
    }

    try:
        bookings = load_bookings()
        bookings.append(booking_copy)

        write_bookings(bookings)

        print("==========================================")
        print("BOOKING KALENDER TERSIMPAN")
        print("FILE:", BOOKING_DATA_FILE)
        print(json.dumps(booking_copy, ensure_ascii=False))
        print("==========================================")

        return True

    except Exception as e:
        print("Gagal menyimpan booking kalender:", e)
        return False


def allowed_file(filename):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_EXTENSIONS


# ============================================================
# MEMBACA DAFTAR ANGGOTA
# ============================================================

def get_members():

    if not os.path.exists(MEMBER_FILE):
        return []

    try:

        with open(
            MEMBER_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

            if isinstance(data, list):
                return data

            return []

    except Exception as e:

        print(
            "Gagal membaca members.json:",
            e
        )

        return []


# ============================================================
# MENYIMPAN DAFTAR ANGGOTA
# ============================================================

def save_members(members):

    with open(
        MEMBER_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            members,
            file,
            ensure_ascii=False,
            indent=4
        )


# ============================================================
# NAMA FILE / FOLDER YANG AMAN
# ============================================================

def safe_filename(nama):

    if nama is None:
        return ""

    nama = str(nama)

    karakter_terlarang = '<>:"/\\|?*'

    for karakter in karakter_terlarang:

        nama = nama.replace(
            karakter,
            "_"
        )

    return nama.strip()


# ============================================================
# FOLDER UPLOAD LOKAL
# ============================================================

def create_member_upload_folder(nama):

    nama_folder = safe_filename(nama)

    folder_path = os.path.join(
        UPLOAD_FOLDER,
        nama_folder
    )

    os.makedirs(
        folder_path,
        exist_ok=True
    )

    return folder_path


# ============================================================
# MEMBUAT CSV ANGGOTA
# ============================================================

def create_member_csv(nama):

    nama_file = safe_filename(nama)

    file_path = os.path.join(
        DATA_FOLDER,
        nama_file + ".csv"
    )

    if not os.path.exists(file_path):

        with open(
            file_path,
            "w",
            encoding="utf-8-sig",
            newline=""
        ) as file:

            writer = csv.writer(file)

            writer.writerow([
                "No",
                "Tanggal",
                "Keterangan",
                "Deadline",
                "Status",
                "File"
            ])

    else:

        try:

            with open(
                file_path,
                "r",
                encoding="utf-8-sig",
                newline=""
            ) as file:

                reader = csv.reader(file)

                rows = list(reader)

            if rows:

                header = rows[0]

                if "File" not in header:

                    header.append("File")

                    for row in rows[1:]:

                        while len(row) < len(header):
                            row.append("")

                    with open(
                        file_path,
                        "w",
                        encoding="utf-8-sig",
                        newline=""
                    ) as file:

                        writer = csv.writer(file)

                        writer.writerows(rows)

        except Exception as e:

            print(
                "Gagal memeriksa struktur CSV:",
                e
            )

    return file_path


# ============================================================
# MEMBACA LOGBOOK
# ============================================================

def get_logbook(nama):

    file_path = create_member_csv(nama)

    try:

        with open(
            file_path,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as file:

            reader = csv.DictReader(file)

            return list(reader)

    except Exception as e:

        print(
            "Gagal membaca logbook:",
            e
        )

        return []


# ============================================================
# MENAMBAHKAN DATA KE CSV
# ============================================================

def add_logbook(
    nama,
    tanggal,
    keterangan,
    deadline,
    status,
    file_name
):

    file_path = create_member_csv(nama)

    data = get_logbook(nama)

    nomor = len(data) + 1

    with open(
        file_path,
        "a",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        writer = csv.writer(file)

        writer.writerow([
            nomor,
            tanggal,
            keterangan,
            deadline,
            status,
            file_name
        ])


# ============================================================
# UPLOAD KE GOOGLE DRIVE
# ============================================================

def upload_to_google_drive(
    uploaded_file,
    nama,
    tanggal
):

    if not uploaded_file:

        print(
            "Tidak ada file yang dikirim."
        )

        return None

    if not uploaded_file.filename:

        print(
            "Nama file kosong."
        )

        return None

    if not allowed_file(
        uploaded_file.filename
    ):

        print(
            "Format file tidak diizinkan:",
            uploaded_file.filename
        )

        return None

    try:

        file_data = uploaded_file.read()

        if not file_data:

            print(
                "File kosong:",
                uploaded_file.filename
            )

            return None

        encoded_file = base64.b64encode(
            file_data
        ).decode("utf-8")

        original_name = secure_filename(
            uploaded_file.filename
        )

        nama_aman = safe_filename(nama)

        tanggal_aman = safe_filename(tanggal)

        final_filename = (
            nama_aman
            + "_"
            + tanggal_aman
            + "_"
            + original_name
        )

        payload = {

            "action": "upload",

            "nama": nama,

            "tanggal": tanggal,

            "filename": final_filename,

            "contentType": (
                uploaded_file.content_type
                or "application/octet-stream"
            ),

            "file": encoded_file
        }

        print(
            "=========================================="
        )

        print(
            "MENGUPLOAD FILE KE GOOGLE DRIVE"
        )

        print(
            "Nama:",
            nama
        )

        print(
            "File:",
            final_filename
        )

        print(
            "Ukuran:",
            len(file_data),
            "bytes"
        )

        print(
            "=========================================="
        )

        response = requests.post(

            GOOGLE_APPS_SCRIPT_UPLOAD_URL,

            json=payload,

            timeout=120

        )

        print(
            "HTTP:",
            response.status_code
        )

        print(
            "Response:",
            response.text
        )

        if response.status_code != 200:

            return None

        try:

            result = response.json()

        except Exception:

            print(
                "Response Google bukan JSON."
            )

            return None

        if result.get("success"):

            return {

                "fileName": result.get(
                    "fileName",
                    final_filename
                ),

                "fileId": result.get(
                    "fileId",
                    ""
                ),

                "fileUrl": result.get(
                    "fileUrl",
                    ""
                )
            }

        print(
            "Google Drive Error:",
            result
        )

        return None

    except requests.exceptions.RequestException as e:

        print(
            "Koneksi ke Google Apps Script gagal:"
        )

        print(e)

        return None

    except Exception as e:

        print(
            "Upload Google Drive gagal:"
        )

        print(e)

        return None


# ============================================================
# HALAMAN ERROR BOOKING
# ============================================================

def booking_error_page(
    title,
    message,
    status_code=500
):

    safe_title = html.escape(
        str(title)
    )

    safe_message = html.escape(
        str(message)
    )

    return f"""
    <!DOCTYPE html>

    <html lang="id">

    <head>

        <meta charset="UTF-8">

        <meta name="viewport" content="width=device-width, initial-scale=1.0">

        <title>{safe_title}</title>

        <style>

            body {{
                font-family: Arial, Helvetica, sans-serif;
                background: #f4f6f8;
                padding: 30px;
            }}

            .box {{
                max-width: 700px;
                margin: 40px auto;
                background: white;
                padding: 30px;
                border-radius: 14px;
                box-shadow: 0 4px 20px rgba(0,0,0,.10);
            }}

            h2 {{
                color: #c62828;
            }}

            .detail {{
                background: #f5f5f5;
                padding: 15px;
                border-radius: 8px;
                white-space: pre-wrap;
                word-break: break-word;
                margin-top: 15px;
            }}

            a {{
                display: inline-block;
                margin-top: 20px;
                padding: 10px 18px;
                background: #222;
                color: white;
                text-decoration: none;
                border-radius: 7px;
            }}

        </style>

    </head>

    <body>

        <div class="box">

            <h2>{safe_title}</h2>

            <p>
                {safe_message}
            </p>

            <div class="detail">
                Periksa terminal Flask untuk melihat
                response lengkap dari Google Apps Script.
            </div>

            <a href="/peminjaman">
                ← Kembali ke Peminjaman
            </a>

        </div>

    </body>

    </html>
    """, status_code


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/",
    methods=["GET", "POST"]
)
def login():

    pesan = ""

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if (
            username == USERNAME
            and password == PASSWORD
        ):

            session["logged_in"] = True

            return redirect(
                url_for("menu_utama")
            )

        pesan = (
            "Username atau password salah."
        )

    return render_template(
        "login.html",
        pesan=pesan
    )


# ============================================================
# MENU UTAMA
# ============================================================

@app.route("/menu")
def menu_utama():

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    return render_template(
        "menu_utama.html"
    )


# ============================================================
# PEMINJAMAN / BOOKING
# ============================================================

@app.route(
    "/peminjaman",
    methods=["GET", "POST"]
)
def peminjaman():

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    # ========================================================
    # PROSES POST BOOKING
    # ========================================================

    if request.method == "POST":

        nama = request.form.get(
            "nama",
            ""
        ).strip()

        nomor_telepon = request.form.get(
            "nomor_telepon",
            ""
        ).strip()

        alat = request.form.get(
            "alat",
            ""
        ).strip()

        # Rentang tanggal peminjaman.
        # "tanggal" tetap dipakai sebagai alias tanggal mulai.
        tanggal_mulai = request.form.get(
            "tanggal_mulai",
            ""
        ).strip()

        tanggal_selesai = request.form.get(
            "tanggal_selesai",
            ""
        ).strip()

        tanggal = tanggal_mulai or request.form.get(
            "tanggal",
            ""
        ).strip()

        jam_mulai = request.form.get(
            "jam_mulai",
            ""
        ).strip()

        jam_selesai = request.form.get(
            "jam_selesai",
            ""
        ).strip()

        keperluan = request.form.get(
            "keperluan",
            ""
        ).strip()

        catatan = request.form.get(
            "catatan",
            ""
        ).strip()

        # ====================================================
        # VALIDASI
        # ====================================================

        if not nama:

            return booking_error_page(
                "Booking Gagal",
                "Nama peminjam wajib dipilih.",
                400
            )

        if not alat:

            return booking_error_page(
                "Booking Gagal",
                "Nama alat wajib diisi.",
                400
            )

        if not tanggal_mulai:
            tanggal_mulai = tanggal

        if not tanggal_selesai:
            tanggal_selesai = tanggal_mulai

        try:
            from datetime import date as _date

            start_date = _date.fromisoformat(tanggal_mulai)
            end_date = _date.fromisoformat(tanggal_selesai)

        except ValueError:
            return booking_error_page(
                "Booking Gagal",
                "Format tanggal peminjaman tidak valid.",
                400
            )

        if end_date < start_date:
            return booking_error_page(
                "Booking Gagal",
                "Tanggal selesai tidak boleh lebih awal "
                "daripada tanggal mulai.",
                400
            )

        if not jam_mulai or not jam_selesai:
            return booking_error_page(
                "Booking Gagal",
                "Jam mulai dan jam selesai wajib diisi.",
                400
            )

        # ====================================================
        # PAYLOAD
        # ====================================================

        payload = {

            "action": "booking",

            "type": "booking",

            "spreadsheetId": (
                GOOGLE_BOOKING_SPREADSHEET_ID
            ),

            "spreadsheetUrl": (
                GOOGLE_BOOKING_SPREADSHEET_URL
            ),

            "nama": nama,

            "nomor_telepon": nomor_telepon,

            "alat": alat,

            # Kompatibilitas: tanggal = tanggal mulai.
            "tanggal": tanggal_mulai,
            "tanggal_mulai": tanggal_mulai,
            "tanggal_selesai": tanggal_selesai,

            "jam_mulai": jam_mulai,

            "jam_selesai": jam_selesai,

            "keperluan": keperluan,

            "catatan": catatan

        }

        # ====================================================
        # SIMPAN LANGSUNG KE DATA KALENDER
        #
        # Kalender membaca bookings.json.
        # Kalender TIDAK membaca Google Spreadsheet.
        # ====================================================

        calendar_saved = save_booking_for_calendar(payload)

        if not calendar_saved:
            return booking_error_page(
                "Booking Gagal",
                "Data peminjaman tidak dapat disimpan ke kalender.",
                500
            )

        print()
        print("=" * 70)
        print("MENGIRIM DATA BOOKING KE GOOGLE APPS SCRIPT")
        print("=" * 70)

        print(
            "URL:",
            GOOGLE_APPS_SCRIPT_BOOKING_URL
        )

        print(
            "PAYLOAD:"
        )

        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2
            )
        )

        print("=" * 70)

        # ====================================================
        # KIRIM KE GOOGLE APPS SCRIPT
        #
        # PERBAIKAN UTAMA:
        #
        # Jangan menggunakan allow_redirects=False.
        #
        # Endpoint Apps Script /exec dapat melakukan redirect
        # internal Google. requests harus menangani redirect
        # tersebut secara otomatis.
        #
        # Gunakan json=payload agar requests membuat body JSON
        # dengan benar.
        # ====================================================

        try:

            response = requests.post(

                GOOGLE_APPS_SCRIPT_BOOKING_URL,

                json=payload,

                headers={
                    "Accept": "application/json"
                },

                timeout=60,

                allow_redirects=True

            )

            print()
            print("RESPONSE GOOGLE APPS SCRIPT")
            print(
                "HTTP:",
                response.status_code
            )

            print(
                "Final URL:",
                response.url
            )

            print(
                "Headers:",
                dict(response.headers)
            )

            print(
                "Body:"
            )

            print(
                response.text
            )

            print("=" * 70)

            # ====================================================
            # CEK HTTP
            # ====================================================

            if not (
                200
                <= response.status_code
                < 300
            ):

                return booking_error_page(
                    "Booking Gagal",
                    (
                        "Google Apps Script mengembalikan "
                        f"HTTP {response.status_code}.\n\n"
                        f"Final URL:\n{response.url}\n\n"
                        f"Response:\n{response.text}"
                    ),
                    502
                )

            # ====================================================
            # PARSE RESPONSE
            # ====================================================

            response_text = (
                response.text.strip()
            )

            if not response_text:

                return booking_error_page(
                    "Booking Gagal",
                    (
                        "Google Apps Script tidak "
                        "mengembalikan response."
                    ),
                    502
                )

            try:

                result = response.json()

            except Exception:

                # ==============================================
                # Kadang Apps Script mengembalikan text biasa.
                # ==============================================

                print(
                    "Response bukan JSON."
                )

                print(
                    response_text
                )

                # ==============================================
                # Jika response mengandung indikator sukses,
                # anggap berhasil.
                # ==============================================

                lower_response = (
                    response_text.lower()
                )

                if (
                    "success" in lower_response
                    and (
                        "true" in lower_response
                        or "berhasil" in lower_response
                    )
                ):

                    result = {
                        "success": True,
                        "message": response_text
                    }

                else:

                    return booking_error_page(
                        "Booking Gagal",
                        (
                            "Google Apps Script mengembalikan "
                            "response yang bukan JSON.\n\n"
                            f"Response:\n{response_text}"
                        ),
                        502
                    )

            print(
                "JSON RESULT:"
            )

            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2
                )
                if isinstance(result, dict)
                else result
            )

            # ====================================================
            # CEK SUCCESS
            # ====================================================

            if isinstance(result, dict):

                success_value = result.get(
                    "success",
                    False
                )

                # ==============================================
                # Antisipasi GAS mengirim "true" sebagai string.
                # ==============================================

                if (
                    success_value is True
                    or str(success_value).lower()
                    == "true"
                ):

                    # Google Sheets tetap diproses seperti biasa.
                    # Setelah berhasil, kembali ke halaman peminjaman
                    # agar kalender langsung membaca bookings.json terbaru.
                    return redirect(url_for("peminjaman", calendar_date=tanggal_mulai))

                message = result.get(
                    "message",
                    result.get(
                        "error",
                        "Google Apps Script menolak data booking."
                    )
                )

            else:

                message = str(result)

            return booking_error_page(
                "Booking Gagal",
                message,
                502
            )

        # ====================================================
        # REQUEST ERROR
        # ====================================================

        except requests.exceptions.RequestException as e:

            print()
            print("=" * 70)
            print("ERROR KONEKSI BOOKING")
            print("=" * 70)
            print(e)
            print("=" * 70)

            return booking_error_page(
                "Koneksi ke Google Apps Script Gagal",
                (
                    "Flask tidak berhasil terhubung "
                    "ke Google Apps Script.\n\n"
                    f"Detail:\n{e}"
                ),
                502
            )

        # ====================================================
        # ERROR LAIN
        # ====================================================

        except Exception as e:

            print()
            print("=" * 70)
            print("BOOKING ERROR")
            print("=" * 70)
            print(e)
            print("=" * 70)

            return booking_error_page(
                "Terjadi Kesalahan",
                (
                    "Sistem gagal memproses booking.\n\n"
                    f"Detail:\n{e}"
                ),
                500
            )

    # ========================================================
    # FORM BOOKING
    # ========================================================
    #
    # Tidak menggunakan render_template.
    # Jadi tidak bergantung pada peminjaman.html.
    # ========================================================

    members = get_members()

    options = ""

    for member in members:

        # members.json diasumsikan berisi:
        #
        # [
        #     "Nama A",
        #     "Nama B"
        # ]
        #
        # Jika ternyata object/dictionary, ambil nama
        # dengan aman.

        if isinstance(member, dict):

            member_name = (
                member.get("nama")
                or member.get("name")
                or member.get("Nama")
                or ""
            )

        else:

            member_name = str(member)

        member_name = member_name.strip()

        if not member_name:
            continue

        safe_member = html.escape(
            member_name,
            quote=True
        )

        options += (
            '<option value="'
            + safe_member
            + '">'
            + safe_member
            + "</option>"
        )

    return f"""
    <!DOCTYPE html>

    <html lang="id">

    <head>

        <meta charset="UTF-8">

        <meta name="viewport" content="width=device-width, initial-scale=1.0">

        <title>Booking / Peminjaman Alat</title>

        <style>

            * {{
                box-sizing: border-box;
            }}

            body {{

                margin: 0;

                padding: 30px;

                font-family:
                    Arial,
                    Helvetica,
                    sans-serif;

                background: #f4f6f8;

            }}

            .container {{

                max-width: 750px;

                margin: auto;

                background: white;

                padding: 30px;

                border-radius: 14px;

                box-shadow:
                    0 4px 20px
                    rgba(0,0,0,.10);

            }}

            h1 {{

                margin-top: 0;

                text-align: center;

            }}

            .info {{

                background: #f0f4f8;

                padding: 12px 15px;

                border-radius: 8px;

                margin-bottom: 22px;

                font-size: 13px;

                color: #555;

            }}

            .form-group {{

                margin-bottom: 18px;

            }}

            label {{

                display: block;

                font-weight: bold;

                margin-bottom: 7px;

            }}

            input,
            select,
            textarea {{

                width: 100%;

                padding: 11px;

                border: 1px solid #ccc;

                border-radius: 7px;

                font-size: 14px;

            }}

            textarea {{

                min-height: 100px;

                resize: vertical;

            }}

            .row {{

                display: grid;

                grid-template-columns:
                    1fr 1fr;

                gap: 15px;

            }}

            button {{

                width: 100%;

                padding: 13px;

                border: none;

                border-radius: 7px;

                background: #222;

                color: white;

                font-size: 16px;

                cursor: pointer;

            }}

            button:hover {{

                background: #444;

            }}

            .back {{

                display: block;

                text-align: center;

                margin-top: 20px;

                color: #333;

                text-decoration: none;

            }}

            /* =====================================================
               KALENDER PEMINJAMAN - MODEL KALENDER DEADLINE
            ===================================================== */

            .calendar-box {{
                margin-top: 30px;
                background: #ffffff;
                border: 1px solid #555;
                border-radius: 0;
                padding: 20px;
            }}

            .calendar-toolbar {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
                margin-bottom: 15px;
            }}

            .calendar-toolbar button {{
                width: auto;
                min-width: 42px;
                padding: 8px 14px;
                background: #2f7d20;
                color: white;
                border: 1px solid #245d19;
                border-radius: 0;
                cursor: pointer;
                font-size: 18px;
            }}

            .calendar-toolbar button:hover {{
                background: #256619;
            }}

            .calendar-title {{
                flex: 1;
                text-align: center;
                font-size: 22px;
                font-weight: bold;
            }}

            .calendar-refresh {{
                font-size: 16px !important;
            }}

            .calendar-table {{
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
            }}

            .calendar-table th {{
                background: #dddddd;
                border: 1px solid #555;
                padding: 10px 5px;
                text-align: center;
                font-weight: bold;
            }}

            .calendar-table td {{
                height: 110px;
                border: 1px solid #777;
                vertical-align: top;
                padding: 6px;
                background: #ffffff;
                overflow: hidden;
            }}

            .calendar-table td.other-month {{
                background: #eeeeee;
                color: #999999;
            }}

            .calendar-table td.today-cell {{
                background: #fffdf0;
            }}

            .calendar-date {{
                font-weight: bold;
                margin-bottom: 5px;
                font-size: 14px;
            }}

            .booking-deadline {{
                background: #ddf0d8;
                border-left: 3px solid #2f7d20;
                padding: 3px 4px;
                margin-top: 3px;
                font-size: 10px;
                line-height: 1.15;
                cursor: pointer;
                overflow: hidden;
                overflow-wrap: anywhere;
                border-radius: 3px;
            }}

            .booking-deadline.today {{
                background: #ff9999;
                border-left-color: #990000;
            }}

            .booking-deadline.soon {{
                background: #ffe0a3;
                border-left-color: #d68a00;
            }}

            .booking-deadline.past {{
                background: #ffdddd;
                border-left-color: #cc0000;
            }}

            .booking-deadline:hover {{
                filter: brightness(0.96);
            }}

            .booking-person {{
                font-weight: 700;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }}

            .booking-detail {{
                margin-top: 1px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }}

            .booking-deadline .booking-detail {{
                font-size: 9px;
            }}

            .booking-status {{
                margin-top: 1px;
                font-size: 9px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }}

            /* =====================================================
               DETAIL + HAPUS BOOKING
            ===================================================== */
            .booking-modal {{
                display: none;
                position: fixed;
                inset: 0;
                z-index: 9999;
                background: rgba(0,0,0,.45);
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}

            .booking-modal.show {{
                display: flex;
            }}

            .booking-modal-card {{
                width: min(500px, 100%);
                background: #ffffff;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 15px 50px rgba(0,0,0,.25);
            }}

            .booking-modal-title {{
                margin: 0 0 14px;
                font-size: 20px;
            }}

            .booking-modal-content {{
                background: #f5f5f5;
                border-radius: 8px;
                padding: 12px;
                white-space: pre-wrap;
                word-break: break-word;
                line-height: 1.45;
            }}

            .booking-modal-actions {{
                display: flex;
                gap: 10px;
                margin-top: 15px;
            }}

            .booking-modal-actions button {{
                width: auto;
                flex: 1;
            }}

            .booking-delete-button {{
                background: #c62828 !important;
            }}

            .booking-delete-button:hover {{
                background: #a51f1f !important;
            }}

            .booking-cancel-button {{
                background: #555 !important;
            }}

            .calendar-empty {{
                padding: 20px;
                text-align: center;
                color: #777;
            }}

            .calendar-legend {{
                margin-top: 12px;
                font-size: 12px;
                color: #555;
            }}

            @media(max-width:600px) {{
                .calendar-box {{
                    padding: 10px;
                }}

                .calendar-table th {{
                    font-size: 11px;
                    padding: 7px 2px;
                }}

                .calendar-table td {{
                    height: 90px;
                    padding: 4px;
                }}

                .booking-deadline {{
                    font-size: 9px;
                    padding: 2px 3px;
                    margin-top: 2px;
                }}

                .calendar-date {{
                    font-size: 12px;
                }}
            }}

            @media(max-width:600px) {{{{

                .row {{{{

                    grid-template-columns: 1fr;

                }}}}

                body {{{{

                    padding: 15px;

                }}}}

                .container {{{{

                    padding: 20px;

                }}}}

            }}}}

        </style>

    </head>

    <body>

        <div class="container">

            <h1>
                Booking / Peminjaman Alat
            </h1>

            <div class="info">

                Data booking akan dikirim langsung
                ke Google Apps Script dan Google Sheets.

            </div>

            <form
                method="POST"
                action="/peminjaman"
            >

                <div class="form-group">

                    <label>
                        Nama Peminjam
                    </label>

                    <input
                        type="text"
                        name="nama"
                        placeholder="Masukkan nama peminjam"
                        required
                        autocomplete="name"
                    >
                </div>
                
                <div class="form-group">

                    <label>
                        Nomor Telepon
                    </label>

                    <input
                        type="tel"
                        name="nomor_telepon"
                        placeholder="Contoh: 081234567890"
                        required
                        autocomplete="tel"
                    >

                </div>
                
                <div class="form-group">

                    <label>
                        Nama Alat
                    </label>

                    <input
                        type="text"
                        name="alat"
                        placeholder="Contoh: XRD, SEM, Furnace"
                        required
                    >

                </div>

                <div class="row">

                    <div class="form-group">

                        <label>
                            Tanggal Mulai
                        </label>

                        <input
                            type="date"
                            id="tanggal_mulai"
                            name="tanggal_mulai"
                            required
                        >

                    </div>

                    <div class="form-group">

                        <label>
                            Tanggal Selesai
                        </label>

                        <input
                            type="date"
                            id="tanggal_selesai"
                            name="tanggal_selesai"
                            required
                        >

                    </div>

                </div>

                <div class="info" style="margin-top:-4px;">
                    Tentukan tanggal dan jam mulai sampai tanggal dan jam selesai.
                    Untuk peminjaman 1 hari, pilih tanggal mulai dan selesai yang sama.
                </div>

                <div class="row">

                    <div class="form-group">

                        <label>
                            Jam Mulai
                        </label>

                        <input
                            type="time"
                            name="jam_mulai"
                            required
                        >

                    </div>

                    <div class="form-group">

                        <label>
                            Jam Selesai
                        </label>

                        <input
                            type="time"
                            name="jam_selesai"
                            required
                        >

                    </div>

                </div>

                <div class="form-group">

                    <label>
                        Keperluan
                    </label>

                    <textarea
                        name="keperluan"
                        placeholder="Tuliskan tujuan penggunaan alat..."
                    ></textarea>

                </div>

                <div class="form-group">

                    <label>
                        Catatan
                    </label>

                    <textarea
                        name="catatan"
                        placeholder="Catatan tambahan..."
                    ></textarea>

                </div>

                <button type="submit">
                    KIRIM BOOKING
                </button>

            </form>

            <!-- =====================================================
                 KALENDER PEMINJAMAN
                 SUMBER DATA TERPISAH DARI GOOGLE SHEETS
            ====================================================== -->

            <div class="calendar-box">

                <div class="calendar-toolbar">

                    <button
                        type="button"
                        onclick="changeCalendarMonth(-1)"
                        title="Bulan sebelumnya"
                    >‹</button>

                    <div
                        id="calendarTitle"
                        class="calendar-title"
                    >Kalender Peminjaman</div>

                    <button
                        type="button"
                        onclick="changeCalendarMonth(1)"
                        title="Bulan berikutnya"
                    >›</button>

                    <button
                        type="button"
                        class="calendar-refresh"
                        onclick="refreshCalendar()"
                        title="Muat ulang kalender"
                    >↻</button>

                </div>

                <table class="calendar-table">

                    <thead>
                        <tr>
                            <th>Minggu</th>
                            <th>Senin</th>
                            <th>Selasa</th>
                            <th>Rabu</th>
                            <th>Kamis</th>
                            <th>Jumat</th>
                            <th>Sabtu</th>
                        </tr>
                    </thead>

                    <tbody id="calendarBody">
                        <tr>
                            <td colspan="7" class="calendar-empty">
                                Memuat jadwal...
                            </td>
                        </tr>
                    </tbody>

                </table>

                <div class="calendar-legend">
                    Hijau = jadwal normal &nbsp; | &nbsp;
                    Kuning = 3 hari lagi &nbsp; | &nbsp;
                    Merah = hari ini / sudah lewat.
                    Klik jadwal untuk melihat detail.
                </div>

            </div>

            <div
                id="bookingModal"
                class="booking-modal"
                aria-hidden="true"
            >
                <div
                    class="booking-modal-card"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="bookingModalTitle"
                    onclick="event.stopPropagation()"
                >
                    <h2
                        id="bookingModalTitle"
                        class="booking-modal-title"
                    >
                        Detail Booking
                    </h2>

                    <div
                        id="bookingModalContent"
                        class="booking-modal-content"
                    ></div>

                    <div class="booking-modal-actions">
                        <button
                            type="button"
                            class="booking-cancel-button"
                            onclick="closeBookingModal()"
                        >
                            Tutup
                        </button>

                        <button
                            type="button"
                            id="bookingDeleteButton"
                            class="booking-delete-button"
                            onclick="deleteCurrentBooking()"
                        >
                            Hapus Booking
                        </button>
                    </div>
                </div>
            </div>

            <script>

                /* =====================================================
                   KALENDER PEMINJAMAN

                   DATA FORM DIBAGI MENJADI 2 JALUR:

                   FORM PEMINJAMAN
                        |
                        +----> GOOGLE SHEETS  (jalur lama)
                        |
                        +----> bookings.json  (jalur kalender)

                   KALENDER HANYA MEMBACA /api/bookings.
                   TIDAK PERNAH MEMBACA GOOGLE SHEETS.
                ===================================================== */

                let calendarBookings = [];

                let calendarDate = new Date();

                const LOCAL_BOOKING_KEY = "nsg_peminjaman_calendar";

                function parseDateLocal(value) {{

                    if (!value) return null;

                    const text = String(value).trim();

                    const match = text.match(
                        /^([0-9]{{4}})[-/]([0-9]{{1,2}})[-/]([0-9]{{1,2}})/
                    );

                    if (match) {{
                        return new Date(
                            Number(match[1]),
                            Number(match[2]) - 1,
                            Number(match[3])
                        );
                    }}

                    const d = new Date(text);
                    return isNaN(d.getTime()) ? null : d;
                }}

                function getBookingStartDate(booking) {{
                    return parseDateLocal(
                        booking.tanggal_mulai ||
                        booking.tanggal ||
                        ""
                    );
                }}

                function getBookingEndDate(booking) {{
                    return parseDateLocal(
                        booking.tanggal_selesai ||
                        booking.tanggal_mulai ||
                        booking.tanggal ||
                        ""
                    );
                }}

                function dateOnly(date) {{
                    if (!date) return null;

                    return new Date(
                        date.getFullYear(),
                        date.getMonth(),
                        date.getDate()
                    );
                }}

                function dateRangeContains(booking, targetDate) {{
                    const start = dateOnly(getBookingStartDate(booking));
                    const end = dateOnly(getBookingEndDate(booking));
                    const target = dateOnly(targetDate);

                    if (!start || !end || !target) return false;

                    return target >= start && target <= end;
                }}

                function formatDateID(date) {{
                    if (!date) return "";

                    return date.toLocaleDateString(
                        "id-ID",
                        {{
                            day: "2-digit",
                            month: "2-digit",
                            year: "numeric"
                        }}
                    );
                }}

                function formatBookingRange(booking) {{
                    const start = getBookingStartDate(booking);
                    const end = getBookingEndDate(booking);

                    if (!start && !end) return "-";

                    const tanggalMulai = start
                        ? formatDateID(start)
                        : "-";

                    const tanggalSelesai = end
                        ? formatDateID(end)
                        : tanggalMulai;

                    const jamMulai =
                        booking.jam_mulai || "-";

                    const jamSelesai =
                        booking.jam_selesai || "-";

                    // Format yang sengaja dibuat eksplisit:
                    // (tanggal mulai : waktu mulai) hingga
                    // (tanggal selesai : waktu selesai)
                    if (start && end && sameDate(start, end)) {{
                        return (
                            "(" +
                            tanggalMulai +
                            " : " +
                            jamMulai +
                            ") hingga (" +
                            tanggalSelesai +
                            " : " +
                            jamSelesai +
                            ")"
                        );
                    }}

                    return (
                        "(" +
                        tanggalMulai +
                        " : " +
                        jamMulai +
                        ") hingga (" +
                        tanggalSelesai +
                        " : " +
                        jamSelesai +
                        ")"
                    );
                }}

                function formatBookingTime(booking) {{
                    const jamMulai = booking.jam_mulai || "";
                    const jamSelesai = booking.jam_selesai || "";

                    if (!jamMulai && !jamSelesai) {{
                        return "";
                    }}

                    if (jamMulai && jamSelesai) {{
                        return jamMulai + " - " + jamSelesai;
                    }}

                    return jamMulai || jamSelesai;
                }}

                function formatBookingDateForCell(booking, cellDate) {{
                    const start = getBookingStartDate(booking);
                    const end = getBookingEndDate(booking);
                    const target = dateOnly(cellDate);

                    if (!target) return "";

                    const startText =
                        start && sameDate(target, start)
                            ? "Mulai " + (booking.jam_mulai || "")
                            : "";

                    const endText =
                        end && sameDate(target, end)
                            ? "Selesai " + (booking.jam_selesai || "")
                            : "";

                    if (startText && endText) {{
                        return startText + " • " + endText;
                    }}

                    if (startText) return startText;
                    if (endText) return endText;

                    return "Masih dipinjam";
                }}

                function sameDate(a, b) {{
                    return a && b &&
                        a.getFullYear() === b.getFullYear() &&
                        a.getMonth() === b.getMonth() &&
                        a.getDate() === b.getDate();
                }}

                function escapeHTML(value) {{
                    const div = document.createElement("div");
                    div.textContent = value == null ? "" : String(value);
                    return div.innerHTML;
                }}

                function formatMonth(date) {{
                    return date.toLocaleDateString(
                        "id-ID",
                        {{
                            month: "long",
                            year: "numeric"
                        }}
                    );
                }}

                function bookingKey(item) {{
                    return [
                        item.nama || "",
                        item.alat || "",
                        item.tanggal_mulai || item.tanggal || "",
                        item.tanggal_selesai || item.tanggal_mulai || item.tanggal || "",
                        item.jam_mulai || "",
                        item.jam_selesai || "",
                        item.nomor_telepon || ""
                    ].join("|");
                }}

                function mergeBookings(serverData, localData) {{

                    const result = [];
                    const seen = new Set();

                    [...serverData, ...localData].forEach(item => {{

                        if (!item || typeof item !== "object") return;

                        const key = bookingKey(item);

                        if (seen.has(key)) return;

                        seen.add(key);
                        result.push(item);
                    }});

                    return result;
                }}

                function readLocalBookings() {{

                    try {{

                        const raw = localStorage.getItem(
                            LOCAL_BOOKING_KEY
                        );

                        if (!raw) return [];

                        const data = JSON.parse(raw);

                        return Array.isArray(data) ? data : [];

                    }} catch (error) {{

                        console.error(
                            "Gagal membaca backup kalender:",
                            error
                        );

                        return [];
                    }}
                }}

                function saveLocalBooking(item) {{

                    try {{

                        const oldData = readLocalBookings();
                        const merged = mergeBookings(oldData, [item]);

                        localStorage.setItem(
                            LOCAL_BOOKING_KEY,
                            JSON.stringify(merged)
                        );

                    }} catch (error) {{

                        console.error(
                            "Gagal menyimpan backup kalender:",
                            error
                        );
                    }}
                }}

                function prepareFormCalendarBackup() {{

                    const form = document.querySelector(
                        'form[action="/peminjaman"]'
                    );

                    if (!form) return;

                    form.addEventListener("submit", function() {{

                        const data = {{
                            nama: form.elements.nama?.value || "",
                            nomor_telepon: form.elements.nomor_telepon?.value || "",
                            alat: form.elements.alat?.value || "",
                            tanggal: form.elements.tanggal_mulai?.value || "",
                            tanggal_mulai: form.elements.tanggal_mulai?.value || "",
                            tanggal_selesai: form.elements.tanggal_selesai?.value || "",
                            jam_mulai: form.elements.jam_mulai?.value || "",
                            jam_selesai: form.elements.jam_selesai?.value || "",
                            keperluan: form.elements.keperluan?.value || "",
                            catatan: form.elements.catatan?.value || ""
                        }};

                        if (data.tanggal) {{
                            saveLocalBooking(data);
                        }}
                    }});
                }}

                function setCalendarFromQuery() {{

                    const params = new URLSearchParams(
                        window.location.search
                    );

                    const selectedDate = params.get("calendar_date");

                    if (!selectedDate) return;

                    const parsed = parseDateLocal(selectedDate);

                    if (parsed) {{
                        calendarDate = new Date(
                            parsed.getFullYear(),
                            parsed.getMonth(),
                            1
                        );
                    }}
                }}

                function changeCalendarMonth(amount) {{

                    calendarDate = new Date(
                        calendarDate.getFullYear(),
                        calendarDate.getMonth() + amount,
                        1
                    );

                    renderCalendar();
                }}

                function daysLeft(bookingDate) {{

                    const today = new Date();

                    today.setHours(0, 0, 0, 0);
                    bookingDate.setHours(0, 0, 0, 0);

                    return Math.round(
                        (bookingDate - today) / 86400000
                    );
                }}

                function statusText(left) {{

                    if (left === 0) {{
                        return "🔴 HARI INI";
                    }}

                    if (left > 0) {{
                        return left + " hari lagi";
                    }}

                    return "⚠️ Terlewat";
                }}

                function statusClass(left) {{

                    if (left === 0) return "today";
                    if (left < 0) return "past";
                    if (left <= 3) return "soon";

                    return "normal";
                }}

                let currentBookingForDelete = null;

                function showBookingDetail(booking) {{

                    currentBookingForDelete = booking;

                    const modal = document.getElementById(
                        "bookingModal"
                    );

                    const content = document.getElementById(
                        "bookingModalContent"
                    );

                    const title = document.getElementById(
                        "bookingModalTitle"
                    );

                    if (!modal || !content || !title) return;

                    title.textContent =
                        "Detail Booking - " +
                        (booking.alat || "Alat");

                    content.textContent = [
                        "Nama: " + (booking.nama || "-"),
                        "Nomor Telepon: " +
                            (booking.nomor_telepon || "-"),
                        "Alat: " + (booking.alat || "-"),
                        "Waktu Peminjaman: " +
                            formatBookingRange(booking),
                        "Keperluan: " +
                            (booking.keperluan || "-"),
                        "Catatan: " +
                            (booking.catatan || "-")
                    ].join("\\n");

                    modal.classList.add("show");
                    modal.setAttribute("aria-hidden", "false");
                }}

                function closeBookingModal() {{

                    const modal = document.getElementById(
                        "bookingModal"
                    );

                    if (modal) {{
                        modal.classList.remove("show");
                        modal.setAttribute(
                            "aria-hidden",
                            "true"
                        );
                    }}

                    currentBookingForDelete = null;
                }}

                async function deleteCurrentBooking() {{

                    if (!currentBookingForDelete) return;

                    const booking = currentBookingForDelete;
                    const id = booking.id;

                    if (!id) {{
                        alert(
                            "Booking lama tidak memiliki ID yang valid. " +
                            "Silakan refresh kalender terlebih dahulu."
                        );
                        return;
                    }}

                    const label =
                        (booking.alat || "Alat") +
                        " - " +
                        (booking.tanggal || "");

                    const confirmed = confirm(
                        "Hapus booking berikut?\\n\\n" +
                        label +
                        "\\n" +
                        (booking.nama || "Tanpa nama") +
                        "\\n\\nData yang sudah dihapus tidak dapat " +
                        "dikembalikan dari kalender."
                    );

                    if (!confirmed) return;

                    const button = document.getElementById(
                        "bookingDeleteButton"
                    );

                    if (button) {{
                        button.disabled = true;
                        button.textContent = "Menghapus...";
                    }}

                    try {{
                        const response = await fetch(
                            "/api/bookings?id=" +
                            encodeURIComponent(id),
                            {{
                                method: "DELETE",
                                cache: "no-store",
                                credentials: "same-origin",
                                headers: {{
                                    "Accept": "application/json"
                                }}
                            }}
                        );

                        const result = await response.json();

                        if (!response.ok || !result.success) {{
                            throw new Error(
                                result.error ||
                                "Booking gagal dihapus."
                            );
                        }}

                        /*
                         * Server adalah sumber data utama.
                         * Setelah delete berhasil, localStorage langsung
                         * disinkronkan agar booking lama tidak muncul lagi
                         * ketika masuk kembali ke halaman peminjaman.
                         */
                        const serverData =
                            Array.isArray(result.bookings)
                                ? result.bookings
                                : [];

                        calendarBookings = serverData;

                        try {{
                            localStorage.setItem(
                                LOCAL_BOOKING_KEY,
                                JSON.stringify(serverData)
                            );
                        }} catch (storageError) {{
                            console.warn(
                                "Gagal sinkronisasi localStorage:",
                                storageError
                            );
                        }}

                        closeBookingModal();
                        renderCalendar();

                    }} catch (error) {{
                        console.error(
                            "Gagal menghapus booking:",
                            error
                        );

                        alert(
                            "Booking gagal dihapus.\\n\\n" +
                            error.message
                        );

                    }} finally {{
                        if (button) {{
                            button.disabled = false;
                            button.textContent = "Hapus Booking";
                        }}
                    }}
                }}



                function renderCalendar() {{

                    const title = document.getElementById(
                        "calendarTitle"
                    );

                    const body = document.getElementById(
                        "calendarBody"
                    );

                    if (!title || !body) return;

                    title.textContent = formatMonth(calendarDate);

                    body.innerHTML = "";

                    const year = calendarDate.getFullYear();
                    const month = calendarDate.getMonth();

                    const firstDay = new Date(year, month, 1);
                    const firstWeekday = firstDay.getDay();
                    const daysInMonth = new Date(
                        year,
                        month + 1,
                        0
                    ).getDate();

                    const previousMonthDays = new Date(
                        year,
                        month,
                        0
                    ).getDate();

                    const totalCells = Math.ceil(
                        (firstWeekday + daysInMonth) / 7
                    ) * 7;

                    const today = new Date();

                    for (
                        let index = 0;
                        index < totalCells;
                        index++
                    ) {{

                        if (index % 7 === 0) {{
                            var row = document.createElement("tr");
                            body.appendChild(row);
                        }}

                        const offset = index - firstWeekday + 1;

                        let cellDate;
                        let otherMonth = false;

                        if (offset < 1) {{

                            cellDate = new Date(
                                year,
                                month - 1,
                                previousMonthDays + offset
                            );

                            otherMonth = true;

                        }} else if (offset > daysInMonth) {{

                            cellDate = new Date(
                                year,
                                month + 1,
                                offset - daysInMonth
                            );

                            otherMonth = true;

                        }} else {{

                            cellDate = new Date(
                                year,
                                month,
                                offset
                            );
                        }}

                        const cell = document.createElement("td");

                        if (otherMonth) {{
                            cell.classList.add("other-month");
                        }}

                        if (sameDate(cellDate, today)) {{
                            cell.classList.add("today-cell");
                        }}

                        const date = document.createElement("div");
                        date.className = "calendar-date";
                        date.textContent = cellDate.getDate();
                        cell.appendChild(date);

                        if (!otherMonth) {{

                            const bookings = calendarBookings.filter(item => {{
                                return dateRangeContains(item, cellDate);
                            }});

                            bookings.forEach(booking => {{

                                // Untuk booking multi-hari, status mengikuti
                                // tanggal yang sedang ditampilkan.
                                const bookingDate = dateOnly(cellDate);

                                const left = daysLeft(bookingDate);

                                const event = document.createElement("div");

                                event.className =
                                    "booking-deadline " +
                                    statusClass(left);

                                event.setAttribute(
                                    "role",
                                    "button"
                                );

                                event.tabIndex = 0;

                                event.onclick = function() {{
                                    showBookingDetail(booking);
                                }};

                                event.onkeydown = function(e) {{
                                    if (e.key === "Enter" || e.key === " ") {{
                                        showBookingDetail(booking);
                                    }}
                                }};

                                const nama = escapeHTML(
                                    booking.nama || "Tanpa nama"
                                );

                                const alat = escapeHTML(
                                    booking.alat || "Alat"
                                );

                                const waktu = escapeHTML(
                                    formatBookingTime(booking)
                                );

                                // Booking multi-hari harus tetap mempunyai
                                // label pada SETIAP tanggal yang termasuk
                                // dalam rentang peminjaman.
                                const posisiTanggal =
                                    escapeHTML(
                                        formatBookingDateForCell(
                                            booking,
                                            cellDate
                                        )
                                    );

                                const startDate = getBookingStartDate(booking);
                                const endDate = getBookingEndDate(booking);
                                const isRange =
                                    startDate &&
                                    endDate &&
                                    !sameDate(startDate, endDate);

                                let rangeLabel = "";

                                if (isRange) {{
                                    rangeLabel =
                                        '<div class="booking-detail">📅 ' +
                                        escapeHTML(formatBookingRange(booking)) +
                                        '</div>';
                                }}

                                event.innerHTML = `
                                    <div class="booking-person">
                                        ${{nama}}
                                    </div>
                                    <div class="booking-detail">
                                        ${{alat}}
                                    </div>
                                    <div class="booking-detail">
                                        🕐 ${{waktu}}
                                    </div>
                                    <div class="booking-detail">
                                        ${{posisiTanggal}}
                                    </div>
                                    ${{rangeLabel}}
                                    <div class="booking-status">
                                        ${{statusText(left)}}
                                    </div>
                                `;

                                cell.appendChild(event);
                            }});
                        }}

                        row.appendChild(cell);
                    }}
                }}

                async function loadCalendarBookings() {{

                    /*
                     * SERVER ADALAH SUMBER DATA UTAMA.
                     *
                     * localStorage hanya dipakai sebagai fallback jika
                     * server/API sedang tidak dapat diakses.
                     *
                     * Versi lama melakukan merge server + localStorage.
                     * Akibatnya booking yang sudah dihapus dari server
                     * bisa muncul lagi dari localStorage. Itu sekarang
                     * sengaja dihilangkan.
                     */
                    const localData = readLocalBookings();

                    try {{

                        const response = await fetch(
                            "/api/bookings?_=" + Date.now(),
                            {{
                                method: "GET",
                                cache: "no-store",
                                credentials: "same-origin",
                                headers: {{
                                    "Accept": "application/json",
                                    "Cache-Control": "no-cache"
                                }}
                            }}
                        );

                        if (!response.ok) {{
                            throw new Error(
                                "API kalender HTTP " +
                                response.status
                            );
                        }}

                        const result = await response.json();

                        if (!result.success) {{
                            throw new Error(
                                result.error ||
                                "API kalender gagal"
                            );
                        }}

                        const serverData =
                            Array.isArray(result.bookings)
                                ? result.bookings
                                : [];

                        /*
                         * Server authoritative.
                         * Ini yang menjamin setelah kembali dari menu,
                         * booking tetap tampil dan booking yang dihapus
                         * tidak hidup kembali.
                         */
                        calendarBookings = serverData;

                        /*
                         * Sinkronkan cache lokal dengan server.
                         * Jangan merge.
                         */
                        try {{
                            localStorage.setItem(
                                LOCAL_BOOKING_KEY,
                                JSON.stringify(serverData)
                            );
                        }} catch (storageError) {{
                            console.warn(
                                "Gagal menyimpan sinkronisasi kalender:",
                                storageError
                            );
                        }}

                        renderCalendar();

                    }} catch (error) {{

                        console.error(
                            "API kalender gagal, menggunakan backup lokal:",
                            error
                        );

                        calendarBookings = localData;
                        renderCalendar();
                    }}
                }}


                async function refreshCalendar() {{

                    const button = document.querySelector(
                        ".calendar-refresh"
                    );

                    if (button) {{
                        button.disabled = true;
                        button.textContent = "⟳";
                    }}

                    try {{
                        await loadCalendarBookings();
                    }} finally {{
                        if (button) {{
                            button.disabled = false;
                            button.textContent = "↻";
                        }}
                    }}
                }}

                document.addEventListener(
                    "DOMContentLoaded",
                    function() {{

                        const startDateInput =
                            document.getElementById("tanggal_mulai");
                        const endDateInput =
                            document.getElementById("tanggal_selesai");

                        if (startDateInput && endDateInput) {{
                            startDateInput.addEventListener("change", function() {{
                                if (!endDateInput.value) {{
                                    endDateInput.value = startDateInput.value;
                                }}

                                endDateInput.min = startDateInput.value || "";
                            }});

                            endDateInput.addEventListener("change", function() {{
                                if (
                                    startDateInput.value &&
                                    endDateInput.value &&
                                    endDateInput.value < startDateInput.value
                                ) {{
                                    alert(
                                        "Tanggal selesai tidak boleh lebih awal " +
                                        "daripada tanggal mulai."
                                    );
                                    endDateInput.value = startDateInput.value;
                                }}
                            }});

                            endDateInput.min = startDateInput.value || "";
                        }}

                        setCalendarFromQuery();
                        prepareFormCalendarBackup();
                        renderCalendar();
                        loadCalendarBookings();

                        const modal = document.getElementById(
                            "bookingModal"
                        );

                        if (modal) {{
                            modal.addEventListener(
                                "click",
                                function(event) {{
                                    if (event.target === modal) {{
                                        closeBookingModal();
                                    }}
                                }}
                            );
                        }}

                        document.addEventListener(
                            "keydown",
                            function(event) {{
                                if (event.key === "Escape") {{
                                    closeBookingModal();
                                }}
                            }}
                        );
                    }}
                );

            </script>

            <a
                class="back"
                href="/menu"
            >
                ← Kembali ke Menu Utama
            </a>

        </div>

    </body>

    </html>
    """


# ============================================================
# API DATA BOOKING UNTUK KALENDER
# ============================================================

@app.route("/api/bookings", methods=["GET", "DELETE", "POST"])
def api_bookings():

    if not session.get("logged_in"):
        return (
            {
                "success": False,
                "error": "Unauthorized"
            },
            401
        )

    # ========================================================
    # HAPUS BOOKING MANUAL
    # ========================================================
    if request.method in ("DELETE", "POST"):
        data = request.get_json(silent=True) or {}

        booking_id_value = (
            request.args.get("id")
            or request.form.get("id")
            or data.get("id")
        )

        booking_id_value = str(
            booking_id_value or ""
        ).strip()

        if not booking_id_value:
            return {
                "success": False,
                "error": "ID booking tidak ditemukan."
            }, 400

        bookings = load_bookings()

        remaining = []
        deleted = 0

        for item in bookings:
            if booking_id(item) == booking_id_value:
                deleted += 1
            else:
                remaining.append(item)

        if deleted == 0:
            return {
                "success": False,
                "error": "Booking tidak ditemukan atau sudah dihapus."
            }, 404

        try:
            write_bookings(remaining)

            print("==========================================")
            print("BOOKING DIHAPUS MANUAL")
            print("ID:", booking_id_value)
            print("JUMLAH:", deleted)
            print("==========================================")

            return {
                "success": True,
                "deleted": deleted,
                "bookings": remaining
            }

        except Exception as e:
            print("Gagal menghapus booking:", e)

            return {
                "success": False,
                "error": "Gagal menyimpan perubahan kalender."
            }, 500

    # ========================================================
    # GET DATA KALENDER
    # ========================================================
    response = app.response_class(
        response=json.dumps(
            {
                "success": True,
                "bookings": load_bookings()
            },
            ensure_ascii=False
        ),
        status=200,
        mimetype="application/json"
    )

    # Jangan izinkan browser menggunakan cache lama.
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


# ============================================================
# STOCK
# ============================================================

@app.route("/stock")
def stock():

    if not session.get("logged_in"):
        return redirect(
            url_for("login")
        )

    return render_template(
        "stock.html"
    )

# ============================================================
# DAFTAR ANGGOTA
# ============================================================

@app.route("/anggota")
def daftar_anggota():

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    members = get_members()

    return render_template(
        "anggota.html",
        members=members
    )


# ============================================================
# TAMBAH ANGGOTA
# ============================================================

@app.route(
    "/tambah_anggota",
    methods=["POST"]
)
def tambah_anggota():

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    nama = request.form.get(
        "nama",
        ""
    ).strip()

    if nama:

        members = get_members()

        if nama not in members:

            members.append(nama)

            save_members(members)

            create_member_csv(nama)

            create_member_upload_folder(nama)

    return redirect(
        url_for("daftar_anggota")
    )


# ============================================================
# HALAMAN FILE
# ============================================================

@app.route("/file")
def file():

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    return render_template(
        "file.html"
    )


# ============================================================
# GOOGLE DRIVE UTAMA
# ============================================================

@app.route("/gdrive")
def gdrive():

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    return redirect(
        GOOGLE_DRIVE_URL
    )


# ============================================================
# GOOGLE DRIVE DARI DASHBOARD ANGGOTA
# ============================================================

@app.route("/anggota/<path:nama>/gdrive")
def anggota_gdrive(nama):
    """
    Route kompatibilitas untuk tombol Google Drive anggota.

    Route ini sengaja menggunakan <path:nama> agar nama anggota yang
    memiliki spasi/karakter URL tidak menyebabkan route Flask 404.
    Setelah route ditemukan, pengguna langsung diarahkan ke Google Drive.
    """
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    return redirect(GOOGLE_DRIVE_URL)


# Alias tambahan untuk dashboard/template versi lama.
# Semua alias diarahkan ke Google Drive yang sama.
@app.route("/anggota/<path:nama>/google-drive")
def anggota_google_drive(nama):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    return redirect(GOOGLE_DRIVE_URL)


@app.route("/anggota/gdrive/<path:nama>")
def anggota_gdrive_terbalik(nama):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    return redirect(GOOGLE_DRIVE_URL)


# ============================================================
# GOOGLE DRIVE - REDIRECT KHUSUS
# ============================================================

@app.route("/anggota/<nama>/drive")
def anggota_drive(nama):

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    members = get_members()

    nama_decoded = str(nama).strip()

    found = False

    for member in members:

        if isinstance(member, dict):

            member_name = (
                member.get("nama")
                or member.get("name")
                or member.get("Nama")
                or ""
            )

        else:

            member_name = str(member)

        if (
            str(member_name).strip()
            == nama_decoded
        ):

            found = True
            break

    if not found:

        return (
            "Anggota tidak ditemukan",
            404
        )

    return redirect(
        GOOGLE_DRIVE_URL
    )


# ============================================================
# DASHBOARD ANGGOTA
# ============================================================

@app.route("/anggota/<nama>")
def dashboard_anggota(nama):

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    members = get_members()

    nama_decoded = str(nama).strip()

    found_member = None

    for member in members:

        if isinstance(member, dict):

            member_name = (
                member.get("nama")
                or member.get("name")
                or member.get("Nama")
                or ""
            )

        else:

            member_name = str(member)

        if (
            str(member_name).strip()
            == nama_decoded
        ):

            found_member = member_name

            break

    if found_member is None:

        return (
            "Anggota tidak ditemukan",
            404
        )

    data = get_logbook(
        found_member
    )

    return render_template(
        "dashboard.html",
        nama=found_member,
        data=data,
        # LANGSUNG KE GOOGLE DRIVE UTAMA.
        # Tidak lagi melewati route Flask, sehingga tombol Google Drive
        # dari dashboard anggota tidak terkena 404 akibat URL route.
        google_drive_url=GOOGLE_DRIVE_URL,
        booking_url=url_for(
            "peminjaman"
        )
    )


# ============================================================
# LOGBOOK
# ============================================================

@app.route("/anggota/<nama>/logbook")
def logbook_anggota(nama):

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    members = get_members()

    nama_decoded = str(nama).strip()

    found_member = None

    for member in members:

        if isinstance(member, dict):

            member_name = (
                member.get("nama")
                or member.get("name")
                or member.get("Nama")
                or ""
            )

        else:

            member_name = str(member)

        if (
            str(member_name).strip()
            == nama_decoded
        ):

            found_member = member_name

            break

    if found_member is None:

        return (
            "Anggota tidak ditemukan",
            404
        )

    data = get_logbook(
        found_member
    )

    return render_template(
        "logbook.html",
        nama=found_member,
        data=data
    )


# ============================================================
# HAPUS LAPORAN
# ============================================================

@app.route(
    "/anggota/<nama>/logbook/hapus/<no>",
    methods=["POST"]
)
def hapus_laporan(nama, no):

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    members = get_members()

    nama_decoded = str(nama).strip()

    found_member = None

    for member in members:

        if isinstance(member, dict):

            member_name = (
                member.get("nama")
                or member.get("name")
                or member.get("Nama")
                or ""
            )

        else:

            member_name = str(member)

        if (
            str(member_name).strip()
            == nama_decoded
        ):

            found_member = member_name

            break

    if found_member is None:

        return (
            "Anggota tidak ditemukan",
            404
        )

    data = get_logbook(
        found_member
    )

    data_baru = []

    laporan_dihapus = None

    ditemukan = False

    for row in data:

        nomor_row = str(
            row.get(
                "No",
                ""
            )
        ).strip()

        if nomor_row == str(no).strip():

            ditemukan = True

            laporan_dihapus = row

            continue

        data_baru.append(row)

    if not ditemukan:

        return (
            "Laporan tidak ditemukan",
            404
        )

    # ========================================================
    # HAPUS FILE LOKAL
    # ========================================================

    if laporan_dihapus:

        file_name = laporan_dihapus.get(
            "File",
            ""
        ).strip()

        if (
            file_name
            and not file_name.startswith("http://")
            and not file_name.startswith("https://")
        ):

            local_files = file_name.split("||")

            upload_folder = (
                create_member_upload_folder(
                    found_member
                )
            )

            for local_file in local_files:

                local_file = local_file.strip()

                if not local_file:
                    continue

                safe_file = secure_filename(
                    local_file
                )

                uploaded_path = os.path.join(
                    upload_folder,
                    safe_file
                )

                if os.path.exists(
                    uploaded_path
                ):

                    try:

                        os.remove(
                            uploaded_path
                        )

                    except Exception as e:

                        print(
                            "Gagal menghapus file lokal:",
                            e
                        )

    # ========================================================
    # TULIS ULANG CSV
    # ========================================================

    file_path = create_member_csv(
        found_member
    )

    with open(
        file_path,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        writer = csv.writer(file)

        writer.writerow([
            "No",
            "Tanggal",
            "Keterangan",
            "Deadline",
            "Status",
            "File"
        ])

        for nomor, row in enumerate(
            data_baru,
            start=1
        ):

            writer.writerow([

                nomor,

                row.get(
                    "Tanggal",
                    ""
                ),

                row.get(
                    "Keterangan",
                    ""
                ),

                row.get(
                    "Deadline",
                    ""
                ),

                row.get(
                    "Status",
                    ""
                ),

                row.get(
                    "File",
                    ""
                )

            ])

    return redirect(
        url_for(
            "logbook_anggota",
            nama=found_member
        )
    )


# ============================================================
# FORM LAPORAN
# ============================================================

@app.route(
    "/anggota/<nama>/form",
    methods=["GET", "POST"]
)
def form_anggota(nama):

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    members = get_members()

    nama_decoded = str(nama).strip()

    found_member = None

    for member in members:

        if isinstance(member, dict):

            member_name = (
                member.get("nama")
                or member.get("name")
                or member.get("Nama")
                or ""
            )

        else:

            member_name = str(member)

        if (
            str(member_name).strip()
            == nama_decoded
        ):

            found_member = member_name

            break

    if found_member is None:

        return (
            "Anggota tidak ditemukan",
            404
        )

    if request.method == "POST":

        tanggal = request.form.get(
            "tanggal",
            ""
        )

        keterangan = request.form.get(
            "keterangan",
            ""
        )

        deadline = request.form.get(
            "deadline",
            ""
        )

        status = request.form.get(
            "status",
            "Pending"
        )

        uploaded_files = request.files.getlist(
            "files"
        )

        drive_links = []

        for uploaded_file in uploaded_files:

            if not uploaded_file:
                continue

            if not uploaded_file.filename:
                continue

            drive_file = upload_to_google_drive(

                uploaded_file,

                found_member,

                tanggal

            )

            if drive_file:

                file_url = drive_file.get(
                    "fileUrl",
                    ""
                )

                if file_url:

                    drive_links.append(
                        file_url
                    )

        file_value = "||".join(
            drive_links
        )

        add_logbook(

            found_member,

            tanggal,

            keterangan,

            deadline,

            status,

            file_value

        )

        return redirect(

            url_for(

                "logbook_anggota",

                nama=found_member

            )

        )

    return render_template(

        "form_laporan.html",

        nama=found_member

    )


# ============================================================
# FILE UPLOAD LOKAL
# ============================================================

@app.route(
    "/uploads/<nama>/<filename>"
)
def uploaded_file(
    nama,
    filename
):

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    folder = create_member_upload_folder(
        nama
    )

    return send_from_directory(
        folder,
        filename
    )


# ============================================================
# FORM LAMA
# ============================================================

@app.route("/form")
def form_laporan():

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    members = get_members()

    if members:

        first_member = members[0]

        if isinstance(first_member, dict):

            first_member = (
                first_member.get("nama")
                or first_member.get("name")
                or first_member.get("Nama")
                or ""
            )

        return redirect(

            url_for(

                "form_anggota",

                nama=first_member

            )

        )

    return "Belum ada anggota."


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ============================================================
# DOWNLOAD LOGBOOK SEBAGAI PDF
# ============================================================

@app.route(
    "/anggota/<nama>/logbook/pdf"
)
def download_logbook_pdf(nama):

    if not session.get("logged_in"):

        return redirect(
            url_for("login")
        )

    members = get_members()

    nama_decoded = str(nama).strip()

    found_member = None

    for member in members:

        if isinstance(member, dict):

            member_name = (
                member.get("nama")
                or member.get("name")
                or member.get("Nama")
                or ""
            )

        else:

            member_name = str(member)

        if (
            str(member_name).strip()
            == nama_decoded
        ):

            found_member = member_name

            break

    if found_member is None:

        return (
            "Anggota tidak ditemukan",
            404
        )

    data = get_logbook(
        found_member
    )

    nama_file = safe_filename(
        found_member
    )

    pdf_path = os.path.join(

        PDF_FOLDER,

        "Logbook_"
        + nama_file
        + ".pdf"

    )

    document = SimpleDocTemplate(

        pdf_path,

        pagesize=landscape(A4),

        rightMargin=25,

        leftMargin=25,

        topMargin=25,

        bottomMargin=25

    )

    styles = getSampleStyleSheet()

    title_style = styles["Title"]

    title_style.alignment = TA_CENTER

    normal_style = styles["Normal"]

    elements = []

    elements.append(

        Paragraph(

            "LOGBOOK LAPORAN",

            title_style

        )

    )

    elements.append(
        Spacer(
            1,
            10
        )
    )

    elements.append(

        Paragraph(

            f"<b>Nama Anggota:</b> "
            f"{html.escape(found_member)}",

            normal_style

        )

    )

    elements.append(
        Spacer(
            1,
            15
        )
    )

    table_data = [

        [

            "No",

            "Tanggal",

            "Keterangan",

            "Deadline",

            "Status",

            "Bukti / File"

        ]

    ]

    for row in data:

        table_data.append(

            [

                row.get(
                    "No",
                    ""
                ),

                row.get(
                    "Tanggal",
                    ""
                ),

                row.get(
                    "Keterangan",
                    ""
                ),

                row.get(
                    "Deadline",
                    ""
                ),

                row.get(
                    "Status",
                    ""
                ),

                row.get(
                    "File",
                    ""
                )

            ]

        )

    table = Table(

        table_data,

        repeatRows=1,

        colWidths=[

            35,

            75,

            330,

            75,

            80,

            150

        ]

    )

    table.setStyle(

        TableStyle(

            [

                (

                    "BACKGROUND",

                    (0, 0),

                    (-1, 0),

                    colors.lightgrey

                ),

                (

                    "TEXTCOLOR",

                    (0, 0),

                    (-1, 0),

                    colors.black

                ),

                (

                    "FONTNAME",

                    (0, 0),

                    (-1, 0),

                    "Helvetica-Bold"

                ),

                (

                    "FONTNAME",

                    (0, 1),

                    (-1, -1),

                    "Helvetica"

                ),

                (

                    "FONTSIZE",

                    (0, 0),

                    (-1, -1),

                    8

                ),

                (

                    "GRID",

                    (0, 0),

                    (-1, -1),

                    0.5,

                    colors.black

                ),

                (

                    "VALIGN",

                    (0, 0),

                    (-1, -1),

                    "TOP"

                ),

                (

                    "ALIGN",

                    (0, 0),

                    (0, -1),

                    "CENTER"

                ),

                (

                    "ALIGN",

                    (4, 1),

                    (4, -1),

                    "CENTER"

                ),

                (

                    "LEFTPADDING",

                    (0, 0),

                    (-1, -1),

                    5

                ),

                (

                    "RIGHTPADDING",

                    (0, 0),

                    (-1, -1),

                    5

                ),

                (

                    "TOPPADDING",

                    (0, 0),

                    (-1, -1),

                    5

                ),

                (

                    "BOTTOMPADDING",

                    (0, 0),

                    (-1, -1),

                    5

                )

            ]

        )

    )

    elements.append(
        table
    )

    document.build(
        elements
    )

    return send_file(

        pdf_path,

        as_attachment=True,

        download_name=(

            "Logbook_"

            + nama_file

            + ".pdf"

        ),

        mimetype="application/pdf"

    )


# ============================================================
# ERROR HANDLER
# ============================================================

@app.errorhandler(404)
def halaman_tidak_ditemukan(error):

    return """
    <!DOCTYPE html>

    <html lang="id">

    <head>

        <meta charset="UTF-8">

        <title>Halaman Tidak Ditemukan</title>

    </head>

    <body style="
        font-family:Arial;
        padding:40px;
    ">

        <h1>
            404
        </h1>

        <p>
            Halaman yang Anda cari tidak ditemukan.
        </p>

        <a href="/menu">
            ← Kembali ke Menu Utama
        </a>

    </body>

    </html>
    """, 404


# ============================================================
# ERROR HANDLER 500
# ============================================================

@app.errorhandler(500)
def server_error(error):

    return """
    <!DOCTYPE html>

    <html lang="id">

    <head>

        <meta charset="UTF-8">

        <title>Server Error</title>

    </head>

    <body style="
        font-family:Arial;
        padding:40px;
    ">

        <h1>
            500
        </h1>

        <p>
            Terjadi kesalahan pada server Flask.
        </p>

        <a href="/menu">
            ← Kembali ke Menu Utama
        </a>

    </body>

    </html>
    """, 500


# ============================================================
# SERVER
# ============================================================
if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )  