import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
import mysql.connector
import bcrypt
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

LOW_STOCK = 50  # alert threshold

PERMISSIONS = {
    "admin":    {"inventory", "products", "production", "sales", "charts", "users", "suppliers", "edit", "pdf"},
    "manager":  {"inventory", "products", "production", "sales", "charts", "users", "suppliers", "edit", "pdf"},
    "operator": {"inventory", "products", "production", "sales", "charts", "suppliers", "edit"},
    "viewer":   {"inventory", "products", "production", "sales", "charts", "suppliers"},
}


# ══════════════════════════════════════════════════════
#  PDF
# ══════════════════════════════════════════════════════
class PDF:
    def __init__(self, db):
        self.db = db

    def _conn(self):
        return mysql.connector.connect(**self.db)

    def _tbl(self, headers, rows):
        data = [headers] + [[str(c) for c in r] for r in rows]
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1a73e8")),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2ff")]),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    def build(self, path, title_txt, query):
        try:
            conn = self._conn()
            df   = pd.read_sql(query, conn)
            conn.close()
            s  = getSampleStyleSheet()
            ts = ParagraphStyle("T", parent=s["Title"], alignment=TA_CENTER, fontSize=18)
            doc = SimpleDocTemplate(path, pagesize=A4,
                                    leftMargin=.5*inch, rightMargin=.5*inch,
                                    topMargin=.75*inch, bottomMargin=.75*inch)
            doc.build([
                Paragraph(title_txt, ts),
                Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                          s["Normal"]),
                Spacer(1, 12),
                self._tbl(list(df.columns), df.values.tolist()),
            ])
            return True
        except Exception as e:
            print("PDF error:", e)
            return False


# ══════════════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MPM System")
        self.geometry("1280x750")
        self.minsize(900, 600)
        self.state("zoomed")   # start maximized

        self.db = dict(host="localhost", user="root",
                       password="root", database="MPM_DB")
        self.pdf = PDF(self.db)
        self.role    = None
        self.me      = None
        self.sidebar = None
        self.content = None

        self._login_screen()

    def conn(self):
        return mysql.connector.connect(**self.db)

    def can(self, p):
        return p in PERMISSIONS.get(self.role, set())

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def _clear_content(self):
        if self.content:
            for w in self.content.winfo_children():
                w.destroy()

    # ══════════════════════════════════════
    #  LOGIN SCREEN
    # ══════════════════════════════════════
    def _login_screen(self):
        self._clear()
        box = ctk.CTkFrame(self, corner_radius=18)
        box.place(relx=.5, rely=.5, anchor="center")

        ctk.CTkLabel(box, text="MPM System",
                     font=("Arial", 26, "bold")).pack(pady=(20, 2))
        ctk.CTkLabel(box, text="Manufacturing Process Manager",
                     font=("Arial", 11), text_color="gray").pack(pady=(0, 14))

        self._eu = ctk.CTkEntry(box, placeholder_text="Username", width=260)
        self._eu.pack(pady=5)
        self._ep = ctk.CTkEntry(box, placeholder_text="Password", show="*", width=260)
        self._ep.pack(pady=5)
        self._ep.bind("<Return>", lambda e: self._do_login())

        ctk.CTkButton(box, text="Login", command=self._do_login,
                      width=260, height=36).pack(pady=(14, 20))

    def _do_login(self):
        u = self._eu.get().strip()
        p = self._ep.get()
        if not u or not p:
            messagebox.showerror("Error", "Fill in both fields.")
            return
        try:
            c = self.conn(); cur = c.cursor()
            # Try with Active column first, fallback without
            try:
                cur.execute(
                    "SELECT Password, Role FROM USERS WHERE Username=%s AND Active=1", (u,))
            except Exception:
                cur.execute(
                    "SELECT Password, Role FROM USERS WHERE Username=%s", (u,))
            row = cur.fetchone(); c.close()
        except Exception as e:
            messagebox.showerror("DB Error", str(e)); return

        if row:
            stored = row[0]
            try:
                ok = bcrypt.checkpw(p.encode(), stored.encode())
            except Exception:
                ok = (p == stored)   # plain-text fallback for legacy passwords
            if ok:
                self.me   = u
                self.role = row[1].lower()
                self._build_shell()
                self._page_home()
                return

        messagebox.showerror("Login Failed", "Invalid username or password.")

    # ══════════════════════════════════════
    #  SHELL
    # ══════════════════════════════════════
    def _build_shell(self):
        self._clear()

        self.sidebar = ctk.CTkFrame(self, width=225, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(self.sidebar, text="⚙ MPM",
                     font=("Arial", 24, "bold")).pack(pady=(28, 2))
        ctk.CTkLabel(self.sidebar,
                     text=f"{self.me}  [{self.role}]",
                     font=("Arial", 11), text_color="gray").pack(pady=(0, 16))

        ctk.CTkFrame(self.sidebar, height=1,
                     fg_color="#333").pack(fill="x", padx=12, pady=(0, 12))

        B = dict(width=195, anchor="w", corner_radius=8,
                 fg_color="transparent", hover_color="#2a2a3e")

        ctk.CTkButton(self.sidebar, text="🏠  Home",
                      command=self._page_home, **B).pack(pady=3)

        if self.can("suppliers"):
            ctk.CTkButton(self.sidebar, text="🚚  Suppliers",
                          command=self._page_suppliers, **B).pack(pady=3)
        if self.can("inventory"):
            ctk.CTkButton(self.sidebar, text="📦  Raw Materials",
                          command=self._page_inventory, **B).pack(pady=3)
        if self.can("products"):
            ctk.CTkButton(self.sidebar, text="🏭  Products",
                          command=self._page_products, **B).pack(pady=3)
        if self.can("production"):
            ctk.CTkButton(self.sidebar, text="⚙️  Production Log",
                          command=self._page_production, **B).pack(pady=3)
        if self.can("sales"):
            ctk.CTkButton(self.sidebar, text="🛒  Sales Log",
                          command=self._page_sales, **B).pack(pady=3)
        if self.can("charts"):
            ctk.CTkButton(self.sidebar, text="📊  Charts",
                          command=self._page_charts, **B).pack(pady=3)
        if self.can("users"):
            ctk.CTkButton(self.sidebar, text="👥  Manage Users",
                          command=self._page_users, **B).pack(pady=3)

        ctk.CTkButton(self.sidebar, text="🔒  Logout",
                      command=self._login_screen,
                      width=195, corner_radius=8,
                      fg_color="transparent", border_width=1,
                      hover_color="#3b0000").pack(side="bottom", pady=20)

        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True)

    # ══════════════════════════════════════
    #  HOME
    # ══════════════════════════════════════
    def _page_home(self):
        self._clear_content()
        p = self.content

        ctk.CTkLabel(p, text=f"Welcome, {self.me} 👋",
                     font=("Arial", 22, "bold")).pack(anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(p, text=datetime.now().strftime("%A, %d %B %Y"),
                     font=("Arial", 12), text_color="gray").pack(anchor="w", padx=24)

        # Stock alerts
        try:
            c = self.conn(); cur = c.cursor()
            cur.execute(
                "SELECT Name, Stock_level, Unit FROM RAW_MATERIALS WHERE Stock_level < %s",
                (LOW_STOCK,))
            low = cur.fetchall(); c.close()
        except Exception:
            low = []

        if low:
            af = ctk.CTkFrame(p, fg_color="#7f1d1d", corner_radius=10)
            af.pack(fill="x", padx=24, pady=(16, 4))
            ctk.CTkLabel(af, text="⚠️  LOW STOCK ALERT",
                         font=("Arial", 13, "bold"),
                         text_color="#fca5a5").pack(anchor="w", padx=14, pady=(10, 2))
            for name, qty, unit in low:
                ctk.CTkLabel(af,
                             text=f"   • {name}: {qty} {unit or ''}  (threshold {LOW_STOCK})",
                             font=("Arial", 11), text_color="#fecaca").pack(anchor="w", padx=14)
            ctk.CTkLabel(af, text="").pack(pady=4)
        else:
            ok = ctk.CTkFrame(p, fg_color="#14532d", corner_radius=10)
            ok.pack(fill="x", padx=24, pady=(16, 4))
            ctk.CTkLabel(ok, text="✅  All stock levels are healthy.",
                         font=("Arial", 12), text_color="#86efac").pack(padx=14, pady=10)

        # Quick stats
        sf = ctk.CTkFrame(p, fg_color="transparent")
        sf.pack(fill="x", padx=24, pady=16)

        stats = []
        try:
            c = self.conn(); cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM RAW_MATERIALS")
            stats.append(("📦 Materials", cur.fetchone()[0]))
            cur.execute("SELECT COUNT(*) FROM PRODUCTS")
            stats.append(("🏭 Products", cur.fetchone()[0]))
            cur.execute("SELECT COUNT(*) FROM PRODUCTION_LOG")
            stats.append(("⚙️ Prod. Logs", cur.fetchone()[0]))
            cur.execute("SELECT COUNT(*) FROM RAW_MATERIALS WHERE Stock_level < %s", (LOW_STOCK,))
            stats.append(("⚠️ Low Stock", cur.fetchone()[0]))
            try:
                cur.execute("SELECT COALESCE(SUM(sl.Quantity * p.Price),0) FROM SALES_LOG sl JOIN PRODUCTS p ON sl.Pid=p.Pid")
                stats.append(("🛒 Total Revenue", f"₹{cur.fetchone()[0]:,}"))
            except Exception:
                pass
            c.close()
        except Exception:
            pass

        for label, val in stats:
            card = ctk.CTkFrame(sf, corner_radius=12, width=165, height=90)
            card.pack(side="left", padx=8)
            card.pack_propagate(False)
            ctk.CTkLabel(card, text=str(val),
                         font=("Arial", 28, "bold")).pack(pady=(16, 0))
            ctk.CTkLabel(card, text=label,
                         font=("Arial", 11), text_color="gray").pack()

    # ══════════════════════════════════════
    #  GENERIC TABLE PAGE
    # ══════════════════════════════════════
    def _make_table_page(self, title, fetch_fn, columns,
                         add_fn=None, edit_fn=None, delete_fn=None,
                         pdf_query=None, pdf_title=None,
                         low_stock_col=None):
        self._clear_content()
        p = self.content

        # Title
        ctk.CTkLabel(p, text=title,
                     font=("Arial", 20, "bold")).pack(anchor="w", padx=20, pady=(16, 4))

        # Search bar (TOP)
        sf = ctk.CTkFrame(p, fg_color="transparent")
        sf.pack(fill="x", padx=20, pady=(0, 6))
        ctk.CTkLabel(sf, text="🔍 Search:").pack(side="left", padx=(0, 6))
        sv = ctk.StringVar()
        ctk.CTkEntry(sf, textvariable=sv, width=320,
                     placeholder_text="Type to filter rows…").pack(side="left")
        if low_stock_col is not None:
            ctk.CTkLabel(sf, text="  🔴 = Low stock",
                         font=("Arial", 11),
                         text_color="#f87171").pack(side="left", padx=12)

        # Treeview
        tf = ctk.CTkFrame(p, corner_radius=10)
        tf.pack(fill="both", expand=True, padx=20, pady=4)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("MPM.Treeview",
                         background="#1a1a2e", foreground="white",
                         fieldbackground="#1a1a2e", rowheight=28)
        style.configure("MPM.Treeview.Heading",
                         background="#2d2d44", foreground="white",
                         font=("Arial", 10, "bold"))
        style.map("MPM.Treeview",
                   background=[("selected", "#1a56db")],
                   foreground=[("selected", "white")])

        tree = ttk.Treeview(tf, columns=columns, show="headings",
                            style="MPM.Treeview")
        vsb = ttk.Scrollbar(tf, orient="vertical",   command=tree.yview)
        hsb = ttk.Scrollbar(tf, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid (row=0, column=1, sticky="ns")
        hsb.grid (row=1, column=0, sticky="ew")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)

        tree.tag_configure("low",    background="#7f1d1d", foreground="#fca5a5")
        tree.tag_configure("normal", background="#1a1a2e", foreground="white")

        for col in columns:
            tree.heading(col, text=col,
                         command=lambda c=col: _sort(c, False))
            tree.column(col, anchor="center", width=140, minwidth=80)

        all_rows = []

        def _load():
            nonlocal all_rows
            try:
                all_rows = fetch_fn()
            except Exception as e:
                messagebox.showerror("DB Error", str(e))
                all_rows = []
            _render()

        def _render(q=""):
            tree.delete(*tree.get_children())
            for row in all_rows:
                if q and q.lower() not in " ".join(str(v) for v in row).lower():
                    continue
                tag = "normal"
                if low_stock_col is not None:
                    try:
                        if float(row[low_stock_col]) < LOW_STOCK:
                            tag = "low"
                    except Exception:
                        pass
                tree.insert("", "end", values=row, tags=(tag,))

        def _sort(col, rev):
            idx = columns.index(col)
            all_rows.sort(
                key=lambda r: (float(r[idx])
                               if str(r[idx]).replace(".", "").replace("-", "").isdigit()
                               else str(r[idx]).lower()),
                reverse=rev)
            _render(sv.get())
            tree.heading(col, command=lambda: _sort(col, not rev))

        sv.trace_add("write", lambda *a: _render(sv.get()))

        # Action buttons (BOTTOM)
        bf = ctk.CTkFrame(p, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(4, 14))

        if add_fn and self.can("edit"):
            ctk.CTkButton(bf, text="➕ Add",
                          command=lambda: add_fn(_load),
                          width=110, fg_color="#166534").pack(side="left", padx=4)

        if edit_fn and self.can("edit"):
            def _do_edit():
                sel = tree.selection()
                if not sel:
                    messagebox.showwarning("Select", "Select a row to edit.")
                    return
                edit_fn(tree.item(sel[0])["values"], _load)
            ctk.CTkButton(bf, text="✏️ Edit",
                          command=_do_edit,
                          width=110, fg_color="#1e3a5f").pack(side="left", padx=4)

        if delete_fn and self.can("edit"):
            def _do_del():
                sel = tree.selection()
                if not sel:
                    messagebox.showwarning("Select", "Select a row to delete.")
                    return
                vals = tree.item(sel[0])["values"]
                if messagebox.askyesno("Confirm Delete",
                                       f"Delete record ID {vals[0]}?"):
                    delete_fn(vals, _load)
            ctk.CTkButton(bf, text="🗑️ Delete",
                          command=_do_del,
                          width=110, fg_color="#7f1d1d").pack(side="left", padx=4)

        ctk.CTkButton(bf, text="🔄 Refresh",
                      command=_load,
                      width=110, fg_color="#374151").pack(side="left", padx=4)

        if pdf_query and self.can("pdf"):
            def _export():
                path = filedialog.asksaveasfilename(
                    defaultextension=".pdf",
                    filetypes=[("PDF files", "*.pdf")])
                if path:
                    ok = self.pdf.build(path, pdf_title or title, pdf_query)
                    if ok:
                        messagebox.showinfo("Exported", "PDF saved successfully!")
                    else:
                        messagebox.showerror("Error", "PDF generation failed.")
            ctk.CTkButton(bf, text="📄 Export PDF",
                          command=_export,
                          width=130, fg_color="#1a73e8").pack(side="right", padx=4)

        _load()

    # ══════════════════════════════════════
    #  DIALOG HELPER
    # ══════════════════════════════════════
    def _dialog(self, title, fields, on_save, prefill=None):
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.grab_set()
        dlg.resizable(False, False)

        widgets = {}
        for i, (lbl, key, wtype) in enumerate(fields):
            ctk.CTkLabel(dlg, text=lbl, anchor="e",
                         width=130).grid(row=i, column=0, padx=12, pady=8, sticky="e")
            if wtype.startswith("option:"):
                opts = wtype.split(":", 1)[1].split(",")
                var  = ctk.StringVar(value=(prefill or {}).get(key, opts[0]))
                ctk.CTkOptionMenu(dlg, values=opts, variable=var,
                                  width=210).grid(row=i, column=1, padx=12, pady=8)
                widgets[key] = var
            else:
                var  = ctk.StringVar(value=str((prefill or {}).get(key, "")))
                show = "*" if wtype == "password" else ""
                ctk.CTkEntry(dlg, textvariable=var, width=210,
                             show=show).grid(row=i, column=1, padx=12, pady=8)
                widgets[key] = var

        n = len(fields)
        ctk.CTkButton(dlg, text="💾 Save",
                      command=lambda: on_save({k: v.get().strip()
                                               for k, v in widgets.items()}, dlg),
                      width=100).grid(row=n, column=0, pady=14, padx=12)
        ctk.CTkButton(dlg, text="Cancel",
                      command=dlg.destroy,
                      width=100, fg_color="gray").grid(row=n, column=1, pady=14, padx=12)

    # ══════════════════════════════════════
    #  SUPPLIERS
    # ══════════════════════════════════════
    def _page_suppliers(self):
        cols = ("Sid", "Name", "Contact")

        def fetch():
            c = self.conn(); cur = c.cursor()
            cur.execute("SELECT Sid, Name, Contact FROM SUPPLIERS")
            r = cur.fetchall(); c.close(); return r

        def add(reload):
            def save(d, dlg):
                if not d["Name"]:
                    messagebox.showwarning("Missing", "Name required.", parent=dlg); return
                c = self.conn(); cur = c.cursor()
                cur.execute("INSERT INTO SUPPLIERS (Name, Contact) VALUES (%s,%s)",
                            (d["Name"], d["Contact"]))
                c.commit(); c.close(); dlg.destroy(); reload()
            self._dialog("Add Supplier",
                         [("Supplier Name", "Name",    "entry"),
                          ("Contact",       "Contact", "entry")], save)

        def edit(vals, reload):
            pf = dict(zip(cols, vals))
            def save(d, dlg):
                if not d["Name"]:
                    messagebox.showwarning("Missing", "Name required.", parent=dlg); return
                c = self.conn(); cur = c.cursor()
                cur.execute("UPDATE SUPPLIERS SET Name=%s, Contact=%s WHERE Sid=%s",
                            (d["Name"], d["Contact"], vals[0]))
                c.commit(); c.close(); dlg.destroy(); reload()
            self._dialog("Edit Supplier",
                         [("Supplier Name", "Name",    "entry"),
                          ("Contact",       "Contact", "entry")], save, pf)

        def delete(vals, reload):
            try:
                c = self.conn(); cur = c.cursor()
                cur.execute("DELETE FROM SUPPLIERS WHERE Sid=%s", (int(vals[0]),))
                c.commit(); c.close(); reload()
            except Exception as e:
                messagebox.showerror("DB Error", str(e))

        self._make_table_page(
            "🚚 Suppliers", fetch, cols,
            add_fn=add, edit_fn=edit, delete_fn=delete,
            pdf_query="SELECT * FROM SUPPLIERS",
            pdf_title="Suppliers Report")

    # ══════════════════════════════════════
    #  RAW MATERIALS
    # ══════════════════════════════════════
    def _page_inventory(self):
        cols = ("Rid", "Name", "Stock_level", "Unit", "Supplier")

        def fetch():
            c = self.conn(); cur = c.cursor()
            try:
                cur.execute("""
                    SELECT rm.Rid, rm.Name, rm.Stock_level, rm.Unit,
                           COALESCE(s.Name, 'N/A') AS Supplier
                    FROM RAW_MATERIALS rm
                    LEFT JOIN SUPPLIERS s ON rm.Sid = s.Sid
                """)
            except Exception:
                cur.execute("SELECT Rid, Name, Stock_level, Unit FROM RAW_MATERIALS")
                rows = cur.fetchall()
                c.close()
                return [r + ('N/A',) for r in rows]
            r = cur.fetchall(); c.close(); return r

        def _supplier_map():
            c = self.conn(); cur = c.cursor()
            cur.execute("SELECT Sid, Name FROM SUPPLIERS")
            rows = cur.fetchall(); c.close()
            return ({n: i for i, n in rows}, ["N/A"] + [n for _, n in rows])

        def add(reload):
            smap, snames = _supplier_map()
            def save(d, dlg):
                if not d["Name"]:
                    messagebox.showwarning("Missing", "Name required.", parent=dlg); return
                try:
                    sl = int(d["Stock_level"])
                except ValueError:
                    messagebox.showwarning("Invalid", "Stock level must be integer.", parent=dlg); return
                sid = smap.get(d["Supplier"]) if d["Supplier"] != "N/A" else None
                c = self.conn(); cur = c.cursor()
                try:
                    cur.execute(
                        "INSERT INTO RAW_MATERIALS (Name,Stock_level,Unit,Sid) VALUES (%s,%s,%s,%s)",
                        (d["Name"], sl, d["Unit"], sid))
                except Exception:
                    cur.execute(
                        "INSERT INTO RAW_MATERIALS (Name,Stock_level,Unit) VALUES (%s,%s,%s)",
                        (d["Name"], sl, d["Unit"]))
                c.commit(); c.close(); dlg.destroy(); reload()
            self._dialog("Add Raw Material",
                         [("Name",        "Name",        "entry"),
                          ("Stock Level", "Stock_level", "entry"),
                          ("Unit",        "Unit",        "entry"),
                          ("Supplier",    "Supplier",    f"option:{','.join(snames)}")], save)

        def edit(vals, reload):
            smap, snames = _supplier_map()
            pf = {"Name": vals[1], "Stock_level": vals[2],
                  "Unit": vals[3], "Supplier": vals[4]}
            def save(d, dlg):
                try:
                    sl = int(d["Stock_level"])
                except ValueError:
                    messagebox.showwarning("Invalid", "Stock level must be integer.", parent=dlg); return
                sid = smap.get(d["Supplier"]) if d["Supplier"] != "N/A" else None
                c = self.conn(); cur = c.cursor()
                try:
                    cur.execute(
                        "UPDATE RAW_MATERIALS SET Name=%s,Stock_level=%s,Unit=%s,Sid=%s WHERE Rid=%s",
                        (d["Name"], sl, d["Unit"], sid, vals[0]))
                except Exception:
                    cur.execute(
                        "UPDATE RAW_MATERIALS SET Name=%s,Stock_level=%s,Unit=%s WHERE Rid=%s",
                        (d["Name"], sl, d["Unit"], vals[0]))
                c.commit(); c.close(); dlg.destroy(); reload()
            self._dialog("Edit Raw Material",
                         [("Name",        "Name",        "entry"),
                          ("Stock Level", "Stock_level", "entry"),
                          ("Unit",        "Unit",        "entry"),
                          ("Supplier",    "Supplier",    f"option:{','.join(snames)}")], save, pf)

        def delete(vals, reload):
            try:
                c = self.conn(); cur = c.cursor()
                cur.execute("DELETE FROM RAW_MATERIALS WHERE Rid=%s", (int(vals[0]),))
                c.commit(); c.close(); reload()
            except Exception as e:
                messagebox.showerror("DB Error", str(e))

        self._make_table_page(
            "📦 Raw Materials", fetch, cols,
            add_fn=add, edit_fn=edit, delete_fn=delete,
            pdf_query="SELECT * FROM RAW_MATERIALS",
            pdf_title="Raw Materials Inventory Report",
            low_stock_col=2)

    # ══════════════════════════════════════
    #  PRODUCTS
    # ══════════════════════════════════════
    def _page_products(self):
        cols = ("Pid", "Name", "Price", "Quantity")

        def fetch():
            c = self.conn(); cur = c.cursor()
            try:
                cur.execute("SELECT Pid, Name, Price, Quantity FROM PRODUCTS")
            except Exception:
                cur.execute("SELECT Pid, Name, Price, 0 FROM PRODUCTS")
            r = cur.fetchall(); c.close(); return r

        def add(reload):
            def save(d, dlg):
                if not d["Name"]:
                    messagebox.showwarning("Missing", "Name required.", parent=dlg); return
                try:
                    pr  = int(d["Price"])
                    qty = int(d["Quantity"])
                except ValueError:
                    messagebox.showwarning("Invalid", "Price and Quantity must be integers.", parent=dlg); return
                c = self.conn(); cur = c.cursor()
                try:
                    cur.execute("INSERT INTO PRODUCTS (Name, Price, Quantity) VALUES (%s,%s,%s)",
                                (d["Name"], pr, qty))
                except Exception:
                    cur.execute("INSERT INTO PRODUCTS (Name, Price) VALUES (%s,%s)",
                                (d["Name"], pr))
                c.commit(); c.close(); dlg.destroy(); reload()
            self._dialog("Add Product",
                         [("Product Name", "Name",     "entry"),
                          ("Price (₹)",    "Price",    "entry"),
                          ("Quantity",     "Quantity", "entry")], save)

        def edit(vals, reload):
            pf = dict(zip(cols, vals))
            def save(d, dlg):
                try:
                    pr  = int(d["Price"])
                    qty = int(d["Quantity"])
                except ValueError:
                    messagebox.showwarning("Invalid", "Price and Quantity must be integers.", parent=dlg); return
                c = self.conn(); cur = c.cursor()
                try:
                    cur.execute("UPDATE PRODUCTS SET Name=%s, Price=%s, Quantity=%s WHERE Pid=%s",
                                (d["Name"], pr, qty, vals[0]))
                except Exception:
                    cur.execute("UPDATE PRODUCTS SET Name=%s, Price=%s WHERE Pid=%s",
                                (d["Name"], pr, vals[0]))
                c.commit(); c.close(); dlg.destroy(); reload()
            self._dialog("Edit Product",
                         [("Product Name", "Name",     "entry"),
                          ("Price (₹)",    "Price",    "entry"),
                          ("Quantity",     "Quantity", "entry")], save, pf)

        def delete(vals, reload):
            try:
                c = self.conn(); cur = c.cursor()
                cur.execute("DELETE FROM PRODUCTS WHERE Pid=%s", (int(vals[0]),))
                c.commit(); c.close(); reload()
            except Exception as e:
                messagebox.showerror("DB Error", str(e))

        self._make_table_page(
            "🏭 Products", fetch, cols,
            add_fn=add, edit_fn=edit, delete_fn=delete,
            pdf_query="SELECT * FROM PRODUCTS",
            pdf_title="Products Report")

    # ══════════════════════════════════════
    #  PRODUCTION LOG
    # ══════════════════════════════════════
    def _page_production(self):
        cols = ("PLid", "Pid", "Product", "Date", "Quantity")

        def fetch():
            c = self.conn(); cur = c.cursor()
            cur.execute("""
                SELECT pl.PLid, pl.Pid, p.Name, pl.Timestamp, pl.Quantity
                FROM PRODUCTION_LOG pl
                JOIN PRODUCTS p ON pl.Pid = p.Pid
                ORDER BY pl.Timestamp DESC
            """)
            r = cur.fetchall(); c.close(); return r

        def _pmap():
            c = self.conn(); cur = c.cursor()
            cur.execute("SELECT Pid, Name FROM PRODUCTS")
            rows = cur.fetchall(); c.close()
            return ({n: i for i, n in rows}, [n for _, n in rows])

        def _get_bom(cur, pid):
            cur.execute("""
                SELECT b.Rid, rm.Name, rm.Stock_level, b.Qty_required
                FROM BOM b JOIN RAW_MATERIALS rm ON b.Rid = rm.Rid
                WHERE b.Pid = %s
            """, (pid,))
            return cur.fetchall()

        def _check_stock(cur, pid, qty):
            bom = _get_bom(cur, pid)
            if not bom:
                return []
            short = []
            for rid, name, stock, req in bom:
                needed = req * qty
                if stock < needed:
                    short.append(f"  • {name}: need {needed:.1f}, only {stock} available")
            return short

        def _deduct(cur, pid, qty, reverse=False):
            bom = _get_bom(cur, pid)
            for rid, name, stock, req in bom:
                change = req * qty
                if reverse:
                    cur.execute(
                        "UPDATE RAW_MATERIALS SET Stock_level = Stock_level + %s WHERE Rid=%s",
                        (change, rid))
                else:
                    cur.execute(
                        "UPDATE RAW_MATERIALS SET Stock_level = Stock_level - %s WHERE Rid=%s",
                        (change, rid))

        def add(reload):
            pm, pnames = _pmap()
            if not pnames:
                messagebox.showwarning("No Products", "Add at least one product first."); return
            def save(d, dlg):
                if not d["Date"] or not d["Quantity"]:
                    messagebox.showwarning("Missing", "All fields required.", parent=dlg); return
                try:
                    qty = int(d["Quantity"])
                    datetime.strptime(d["Date"], "%Y-%m-%d")
                except ValueError:
                    messagebox.showwarning("Invalid",
                        "Quantity must be integer, Date must be YYYY-MM-DD", parent=dlg); return
                pid = pm[d["Product"]]
                c = self.conn(); cur = c.cursor()
                short = _check_stock(cur, pid, qty)
                if short:
                    c.close()
                    messagebox.showerror("Insufficient Stock",
                        "Not enough raw materials:\n" + "\n".join(short), parent=dlg); return
                cur.execute(
                    "INSERT INTO PRODUCTION_LOG (Pid,Timestamp,Quantity) VALUES (%s,%s,%s)",
                    (pid, d["Date"], qty))
                _deduct(cur, pid, qty)
                # Increase product quantity
                try:
                    cur.execute(
                        "UPDATE PRODUCTS SET Quantity = Quantity + %s WHERE Pid=%s",
                        (qty, pid))
                except Exception:
                    pass
                c.commit(); c.close(); dlg.destroy()
                messagebox.showinfo("Success", "Production logged & stock deducted!")
                reload()
            self._dialog("Add Production Log",
                         [("Product",          "Product",  f"option:{','.join(pnames)}"),
                          ("Date (YYYY-MM-DD)", "Date",     "entry"),
                          ("Quantity",          "Quantity", "entry")], save)

        def edit(vals, reload):
            # vals = (PLid, Pid, Product, Date, Quantity)
            pm, pnames = _pmap()
            pf = {"Product": vals[2], "Date": str(vals[3]), "Quantity": vals[4]}
            def save(d, dlg):
                try:
                    qty_new = int(d["Quantity"])
                    datetime.strptime(d["Date"], "%Y-%m-%d")
                except ValueError:
                    messagebox.showwarning("Invalid",
                        "Quantity must be integer, Date must be YYYY-MM-DD", parent=dlg); return
                pid_new = pm[d["Product"]]
                c = self.conn(); cur = c.cursor()
                cur.execute("SELECT Pid, Quantity FROM PRODUCTION_LOG WHERE PLid=%s", (vals[0],))
                old = cur.fetchone()
                if old:
                    _deduct(cur, old[0], old[1], reverse=True)
                short = _check_stock(cur, pid_new, qty_new)
                if short:
                    if old:
                        _deduct(cur, old[0], old[1])
                    c.commit(); c.close()
                    messagebox.showerror("Insufficient Stock",
                        "Not enough raw materials:\n" + "\n".join(short), parent=dlg); return
                cur.execute(
                    "UPDATE PRODUCTION_LOG SET Pid=%s,Timestamp=%s,Quantity=%s WHERE PLid=%s",
                    (pid_new, d["Date"], qty_new, vals[0]))
                _deduct(cur, pid_new, qty_new)
                # Adjust product quantities
                try:
                    if old:
                        cur.execute(
                            "UPDATE PRODUCTS SET Quantity = Quantity - %s WHERE Pid=%s",
                            (old[1], old[0]))
                    cur.execute(
                        "UPDATE PRODUCTS SET Quantity = Quantity + %s WHERE Pid=%s",
                        (qty_new, pid_new))
                except Exception:
                    pass
                c.commit(); c.close(); dlg.destroy()
                messagebox.showinfo("Success", "Production updated & stock adjusted!")
                reload()
            self._dialog("Edit Production Log",
                         [("Product",          "Product",  f"option:{','.join(pnames)}"),
                          ("Date (YYYY-MM-DD)", "Date",     "entry"),
                          ("Quantity",          "Quantity", "entry")], save, pf)

        def delete(vals, reload):
            # vals[0] = PLid, vals[1] = Pid, vals[4] = Quantity
            try:
                c = self.conn(); cur = c.cursor()
                cur.execute(
                    "SELECT Pid, Quantity FROM PRODUCTION_LOG WHERE PLid=%s", (vals[0],))
                old = cur.fetchone()
                if old:
                    _deduct(cur, old[0], old[1], reverse=True)
                    # Reduce product quantity back
                    try:
                        cur.execute(
                            "UPDATE PRODUCTS SET Quantity = Quantity - %s WHERE Pid=%s",
                            (old[1], old[0]))
                    except Exception:
                        pass
                cur.execute("DELETE FROM PRODUCTION_LOG WHERE PLid=%s", (vals[0],))
                c.commit(); c.close()
                reload()
            except Exception as e:
                messagebox.showerror("DB Error", str(e))

        self._make_table_page(
            "⚙️ Production Log", fetch, cols,
            add_fn=add, edit_fn=edit, delete_fn=delete,
            pdf_query="""
                SELECT pl.PLid, p.Name AS Product,
                       pl.Timestamp AS Date, pl.Quantity
                FROM PRODUCTION_LOG pl
                JOIN PRODUCTS p ON pl.Pid=p.Pid
                ORDER BY pl.Timestamp DESC
            """,
            pdf_title="Production Log Report")

    # ══════════════════════════════════════
    #  SALES LOG
    # ══════════════════════════════════════
    def _page_sales(self):
        cols = ("Slid", "Pid", "Product", "Date", "Quantity", "Total (₹)")

        def fetch():
            c = self.conn(); cur = c.cursor()
            cur.execute("""
                SELECT sl.Slid, sl.Pid, p.Name, sl.Timestamp,
                       sl.Quantity, (sl.Quantity * p.Price) AS Total
                FROM SALES_LOG sl
                JOIN PRODUCTS p ON sl.Pid = p.Pid
                ORDER BY sl.Timestamp DESC
            """)
            r = cur.fetchall(); c.close(); return r

        def _pmap():
            c = self.conn(); cur = c.cursor()
            cur.execute("SELECT Pid, Name, Price, Quantity FROM PRODUCTS")
            rows = cur.fetchall(); c.close()
            name_to_pid   = {n: i   for i, n, pr, q in rows}
            name_to_stock = {n: q   for i, n, pr, q in rows}
            pnames = [n for _, n, _, _ in rows]
            return name_to_pid, name_to_stock, pnames

        def add(reload):
            pm, stock_map, pnames = _pmap()
            if not pnames:
                messagebox.showwarning("No Products", "Add at least one product first."); return
            def save(d, dlg):
                if not d["Date"] or not d["Quantity"]:
                    messagebox.showwarning("Missing", "All fields required.", parent=dlg); return
                try:
                    qty = int(d["Quantity"])
                    datetime.strptime(d["Date"], "%Y-%m-%d")
                except ValueError:
                    messagebox.showwarning("Invalid",
                        "Quantity must be integer, Date must be YYYY-MM-DD", parent=dlg); return
                pid   = pm[d["Product"]]
                stock = stock_map[d["Product"]]
                if qty > stock:
                    messagebox.showerror("Insufficient Stock",
                        f"Only {stock} units of '{d['Product']}' available.", parent=dlg); return
                c = self.conn(); cur = c.cursor()
                cur.execute(
                    "INSERT INTO SALES_LOG (Pid,Timestamp,Quantity) VALUES (%s,%s,%s)",
                    (pid, d["Date"], qty))
                # Decrease product quantity
                try:
                    cur.execute(
                        "UPDATE PRODUCTS SET Quantity = Quantity - %s WHERE Pid=%s",
                        (qty, pid))
                except Exception:
                    pass
                c.commit(); c.close(); dlg.destroy()
                messagebox.showinfo("Success", "Sale recorded & stock updated!")
                reload()
            self._dialog("Add Sale",
                         [("Product",          "Product",  f"option:{','.join(pnames)}"),
                          ("Date (YYYY-MM-DD)", "Date",     "entry"),
                          ("Quantity",          "Quantity", "entry")], save)

        def edit(vals, reload):
            # vals = (Slid, Pid, Product, Date, Quantity, Total)
            pm, stock_map, pnames = _pmap()
            pf = {"Product": vals[2], "Date": str(vals[3]), "Quantity": vals[4]}
            def save(d, dlg):
                try:
                    qty_new = int(d["Quantity"])
                    datetime.strptime(d["Date"], "%Y-%m-%d")
                except ValueError:
                    messagebox.showwarning("Invalid",
                        "Quantity must be integer, Date must be YYYY-MM-DD", parent=dlg); return
                pid_new = pm[d["Product"]]
                c = self.conn(); cur = c.cursor()
                # Restore old product stock
                cur.execute(
                    "SELECT Pid, Quantity FROM SALES_LOG WHERE Slid=%s", (vals[0],))
                old = cur.fetchone()
                if old:
                    try:
                        cur.execute(
                            "UPDATE PRODUCTS SET Quantity = Quantity + %s WHERE Pid=%s",
                            (old[1], old[0]))
                    except Exception:
                        pass
                # Check new stock
                cur.execute("SELECT Quantity FROM PRODUCTS WHERE Pid=%s", (pid_new,))
                row = cur.fetchone()
                avail = row[0] if row else 0
                if qty_new > avail:
                    # Revert restore
                    if old:
                        try:
                            cur.execute(
                                "UPDATE PRODUCTS SET Quantity = Quantity - %s WHERE Pid=%s",
                                (old[1], old[0]))
                        except Exception:
                            pass
                    c.commit(); c.close()
                    messagebox.showerror("Insufficient Stock",
                        f"Only {avail} units available.", parent=dlg); return
                cur.execute(
                    "UPDATE SALES_LOG SET Pid=%s,Timestamp=%s,Quantity=%s WHERE Slid=%s",
                    (pid_new, d["Date"], qty_new, vals[0]))
                try:
                    cur.execute(
                        "UPDATE PRODUCTS SET Quantity = Quantity - %s WHERE Pid=%s",
                        (qty_new, pid_new))
                except Exception:
                    pass
                c.commit(); c.close(); dlg.destroy()
                messagebox.showinfo("Success", "Sale updated!")
                reload()
            self._dialog("Edit Sale",
                         [("Product",          "Product",  f"option:{','.join(pnames)}"),
                          ("Date (YYYY-MM-DD)", "Date",     "entry"),
                          ("Quantity",          "Quantity", "entry")], save, pf)

        def delete(vals, reload):
            try:
                c = self.conn(); cur = c.cursor()
                cur.execute(
                    "SELECT Pid, Quantity FROM SALES_LOG WHERE Slid=%s", (vals[0],))
                old = cur.fetchone()
                if old:
                    try:
                        cur.execute(
                            "UPDATE PRODUCTS SET Quantity = Quantity + %s WHERE Pid=%s",
                            (old[1], old[0]))
                    except Exception:
                        pass
                cur.execute("DELETE FROM SALES_LOG WHERE Slid=%s", (int(vals[0]),))
                c.commit(); c.close(); reload()
            except Exception as e:
                messagebox.showerror("DB Error", str(e))

        self._make_table_page(
            "🛒 Sales Log", fetch, cols,
            add_fn=add, edit_fn=edit, delete_fn=delete,
            pdf_query="""
                SELECT sl.Slid, sl.Pid, p.Name AS Product,
                       sl.Timestamp AS Date, sl.Quantity,
                       (sl.Quantity * p.Price) AS Total
                FROM SALES_LOG sl JOIN PRODUCTS p ON sl.Pid=p.Pid
                ORDER BY sl.Timestamp DESC
            """,
            pdf_title="Sales Log Report")

    # ══════════════════════════════════════
    #  CHARTS
    # ══════════════════════════════════════
    def _page_charts(self):
        self._clear_content()
        p = self.content

        ctk.CTkLabel(p, text="📊 Charts & Analytics",
                     font=("Arial", 20, "bold")).pack(anchor="w", padx=20, pady=(16, 8))

        tab = ctk.CTkTabview(p)
        tab.pack(fill="both", expand=True, padx=20, pady=8)
        tab.add("Stock Distribution")
        tab.add("Production Volume")
        tab.add("Sales Revenue")

        self._chart_stock(tab.tab("Stock Distribution"))
        self._chart_production(tab.tab("Production Volume"))
        self._chart_sales(tab.tab("Sales Revenue"))

    def _chart_stock(self, parent):
        try:
            c = self.conn()
            df = pd.read_sql("SELECT Name, Stock_level FROM RAW_MATERIALS", c)
            c.close()
        except Exception as e:
            ctk.CTkLabel(parent, text=f"Error: {e}").pack(); return

        if df.empty:
            ctk.CTkLabel(parent, text="No data.").pack(); return

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5), facecolor="#1a1a2e")
        for ax in (ax1, ax2):
            ax.set_facecolor("#1a1a2e")

        low_mask = df["Stock_level"] < LOW_STOCK
        col_list = ["#f87171" if v else "#60a5fa" for v in low_mask]
        explode  = [0.06 if v else 0 for v in low_mask]

        ax1.pie(df["Stock_level"], labels=df["Name"],
                autopct="%1.1f%%", startangle=140,
                colors=col_list, explode=explode,
                textprops={"color": "white", "fontsize": 9})
        ax1.set_title("Stock Share  (🔴 = Low)", color="white", fontsize=12)

        ax2.bar(df["Name"], df["Stock_level"], color=col_list, edgecolor="#333")
        ax2.axhline(LOW_STOCK, color="#fbbf24", linestyle="--", linewidth=1.5,
                    label=f"Threshold ({LOW_STOCK})")
        ax2.set_title("Stock Levels", color="white", fontsize=12)
        ax2.set_ylabel("Units", color="white")
        ax2.tick_params(colors="white")
        ax2.legend(facecolor="#1a1a2e", labelcolor="white")
        for sp in ax2.spines.values():
            sp.set_edgecolor("#444")

        fig.tight_layout(pad=2)
        FigureCanvasTkAgg(fig, master=parent).get_tk_widget().pack(fill="both", expand=True)

    def _chart_production(self, parent):
        try:
            c = self.conn()
            df = pd.read_sql("""
                SELECT p.Name AS Product, SUM(pl.Quantity) AS Total
                FROM PRODUCTION_LOG pl JOIN PRODUCTS p ON pl.Pid=p.Pid
                GROUP BY p.Name
            """, c)
            c.close()
        except Exception as e:
            ctk.CTkLabel(parent, text=f"Error: {e}").pack(); return

        if df.empty:
            ctk.CTkLabel(parent, text="No data.").pack(); return

        palette = ["#60a5fa","#34d399","#a78bfa","#fbbf24",
                   "#f87171","#38bdf8","#fb923c","#a3e635"]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5), facecolor="#1a1a2e")
        for ax in (ax1, ax2):
            ax.set_facecolor("#1a1a2e")

        clrs = palette[:len(df)]
        ax1.pie(df["Total"], labels=df["Product"],
                autopct="%1.1f%%", startangle=140, colors=clrs,
                textprops={"color": "white", "fontsize": 9})
        ax1.set_title("Production Share", color="white", fontsize=12)

        ax2.bar(df["Product"], df["Total"], color=clrs, edgecolor="#333")
        ax2.set_title("Units Produced", color="white", fontsize=12)
        ax2.set_ylabel("Quantity", color="white")
        ax2.tick_params(colors="white")
        for sp in ax2.spines.values():
            sp.set_edgecolor("#444")

        fig.tight_layout(pad=2)
        FigureCanvasTkAgg(fig, master=parent).get_tk_widget().pack(fill="both", expand=True)

    def _chart_sales(self, parent):
        try:
            c = self.conn()
            df = pd.read_sql("""
                SELECT p.Name AS Product,
                       SUM(sl.Quantity) AS Units_Sold,
                       SUM(sl.Quantity * p.Price) AS Revenue
                FROM SALES_LOG sl JOIN PRODUCTS p ON sl.Pid=p.Pid
                GROUP BY p.Name
            """, c)
            c.close()
        except Exception as e:
            ctk.CTkLabel(parent, text=f"Error: {e}").pack(); return

        if df.empty:
            ctk.CTkLabel(parent, text="No sales data yet.",
                         font=("Arial", 13), text_color="gray").pack(expand=True)
            return

        palette = ["#60a5fa","#34d399","#a78bfa","#fbbf24",
                   "#f87171","#38bdf8","#fb923c","#a3e635"]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5), facecolor="#1a1a2e")
        for ax in (ax1, ax2):
            ax.set_facecolor("#1a1a2e")

        clrs = palette[:len(df)]
        ax1.pie(df["Revenue"], labels=df["Product"],
                autopct="%1.1f%%", startangle=140, colors=clrs,
                textprops={"color": "white", "fontsize": 9})
        ax1.set_title("Revenue Share", color="white", fontsize=12)

        ax2.bar(df["Product"], df["Revenue"], color=clrs, edgecolor="#333")
        ax2.set_title("Total Revenue (₹)", color="white", fontsize=12)
        ax2.set_ylabel("₹", color="white")
        ax2.tick_params(colors="white")
        for sp in ax2.spines.values():
            sp.set_edgecolor("#444")

        fig.tight_layout(pad=2)
        FigureCanvasTkAgg(fig, master=parent).get_tk_widget().pack(fill="both", expand=True)

    # ══════════════════════════════════════
    #  MANAGE USERS
    # ══════════════════════════════════════
    def _page_users(self):
        self._clear_content()
        p = self.content

        ctk.CTkLabel(p, text="👥 Manage Users",
                     font=("Arial", 20, "bold")).pack(anchor="w", padx=20, pady=(16, 8))

        # Form
        form = ctk.CTkFrame(p, corner_radius=10)
        form.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(form, text="Create / Update User",
                     font=("Arial", 13, "bold")).grid(
            row=0, column=0, columnspan=6, sticky="w", padx=14, pady=(10, 6))

        ctk.CTkLabel(form, text="Username").grid(row=1, column=0, padx=8, pady=6, sticky="e")
        eu = ctk.CTkEntry(form, width=155); eu.grid(row=1, column=1, padx=8)

        ctk.CTkLabel(form, text="Password").grid(row=1, column=2, padx=8, sticky="e")
        ep = ctk.CTkEntry(form, width=155, show="*"); ep.grid(row=1, column=3, padx=8)

        ctk.CTkLabel(form, text="Role").grid(row=1, column=4, padx=8, sticky="e")
        allowed = (["admin","manager","operator","viewer"]
                   if self.role == "admin" else ["operator","viewer"])
        rv = ctk.StringVar(value=allowed[0])
        ctk.CTkOptionMenu(form, values=allowed, variable=rv,
                          width=130).grid(row=1, column=5, padx=8)

        # User table
        tf = ctk.CTkFrame(p, corner_radius=10)
        tf.pack(fill="both", expand=True, padx=20, pady=(0, 6))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("U.Treeview",
                         background="#1a1a2e", foreground="white",
                         fieldbackground="#1a1a2e", rowheight=28)
        style.configure("U.Treeview.Heading",
                         background="#2d2d44", foreground="white",
                         font=("Arial", 10, "bold"))
        style.map("U.Treeview", background=[("selected","#1a56db")])

        ucols = ("Uid", "Username", "Role", "Active")
        tree  = ttk.Treeview(tf, columns=ucols, show="headings", style="U.Treeview")
        for col in ucols:
            tree.heading(col, text=col)
            tree.column(col, anchor="center", width=170)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        tree.tag_configure("inactive", foreground="#6b7280")

        def _refresh():
            tree.delete(*tree.get_children())
            try:
                c = self.conn(); cur = c.cursor()
                try:
                    cur.execute(
                        "SELECT Uid, Username, Role, Active FROM USERS ORDER BY Username")
                    for row in cur.fetchall():
                        tag = "inactive" if not row[3] else ""
                        tree.insert("", "end",
                                    values=(row[0], row[1], row[2],
                                            "Yes" if row[3] else "No"),
                                    tags=(tag,))
                except Exception:
                    cur.execute("SELECT Uid, Username, Role FROM USERS ORDER BY Username")
                    for row in cur.fetchall():
                        tree.insert("", "end",
                                    values=(row[0], row[1], row[2], "N/A"))
                c.close()
            except Exception as e:
                messagebox.showerror("DB Error", str(e))

        def _fill(event=None):
            sel = tree.selection()
            if not sel: return
            vals = tree.item(sel[0])["values"]
            eu.delete(0, "end"); eu.insert(0, str(vals[1]))
            if str(vals[2]) in allowed: rv.set(str(vals[2]))

        tree.bind("<<TreeviewSelect>>", _fill)

        def _save():
            uname = eu.get().strip()
            pwd   = ep.get()
            role  = rv.get()
            if not uname:
                messagebox.showwarning("Missing", "Username is required."); return
            if not pwd:
                messagebox.showwarning("Missing", "Password is required."); return
            if len(pwd) < 6:
                messagebox.showwarning("Weak", "Password must be ≥ 6 characters."); return
            hashed = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()
            try:
                c = self.conn(); cur = c.cursor()
                try:
                    cur.execute(
                        "INSERT INTO USERS (Username,Password,Role,Active) "
                        "VALUES (%s,%s,%s,1) "
                        "ON DUPLICATE KEY UPDATE Password=%s,Role=%s,Active=1",
                        (uname, hashed, role, hashed, role))
                except Exception:
                    cur.execute(
                        "INSERT INTO USERS (Username,Password,Role) "
                        "VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE Password=%s,Role=%s",
                        (uname, hashed, role, hashed, role))
                c.commit(); c.close()
                messagebox.showinfo("Saved", f"User '{uname}' saved as '{role}'.")
                eu.delete(0, "end"); ep.delete(0, "end")
                _refresh()
            except Exception as e:
                messagebox.showerror("DB Error", str(e))

        def _toggle():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Select", "Select a user first."); return
            vals = tree.item(sel[0])["values"]
            if str(vals[1]) == self.me:
                messagebox.showwarning("Denied", "Cannot deactivate yourself."); return
            try:
                c = self.conn(); cur = c.cursor()
                cur.execute("UPDATE USERS SET Active = 1-Active WHERE Uid=%s", (vals[0],))
                c.commit(); c.close(); _refresh()
            except Exception as e:
                messagebox.showerror("DB Error", str(e))

        def _del_user():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Select", "Select a user first."); return
            vals = tree.item(sel[0])["values"]
            if str(vals[1]) == self.me:
                messagebox.showwarning("Denied", "Cannot delete yourself."); return
            if messagebox.askyesno("Confirm", f"Delete user '{vals[1]}'?"):
                try:
                    c = self.conn(); cur = c.cursor()
                    cur.execute("DELETE FROM USERS WHERE Uid=%s", (vals[0],))
                    c.commit(); c.close(); _refresh()
                except Exception as e:
                    messagebox.showerror("DB Error", str(e))

        # Buttons
        bf = ctk.CTkFrame(p, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(2, 14))
        ctk.CTkButton(bf, text="💾 Save User",
                      command=_save, width=130,
                      fg_color="#166534").pack(side="left", padx=4)
        ctk.CTkButton(bf, text="🔄 Toggle Active",
                      command=_toggle, width=150,
                      fg_color="#92400e").pack(side="left", padx=4)
        ctk.CTkButton(bf, text="🗑️ Delete User",
                      command=_del_user, width=130,
                      fg_color="#7f1d1d").pack(side="left", padx=4)
        ctk.CTkButton(bf, text="🔄 Refresh",
                      command=_refresh, width=110,
                      fg_color="#374151").pack(side="left", padx=4)

        _refresh()


# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    app = App()
    app.mainloop()