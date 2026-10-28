"""Desktop review window. All files are processed on this computer."""
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from protocol_excel import FIELDS, Record, extract, report_text, validate, write_excel


class App:
    def __init__(self, root):
        self.root = root
        self.records: list[Record] = []
        self.current = None
        self.reviewed: set[int] = set()
        self.loading = False
        self.busy = False
        root.title("Протокол → Excel")
        root.geometry("1120x820")
        root.minsize(920, 720)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        top = ttk.Frame(root, padding=12)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Excel с вашей таблицей:").grid(row=0, column=0, sticky="w")
        default = Path(__file__).parent / "Шаблон.xlsx"
        self.template = tk.StringVar(value=str(default) if default.exists() else "")
        ttk.Entry(top, textvariable=self.template).grid(row=0, column=1, padx=8, sticky="ew")
        ttk.Button(top, text="Выбрать Excel…", command=self.choose_template).grid(row=0, column=2)
        ttk.Label(top, text="1. Выберите документы.  2. Проверьте поля и предупреждения.  3. Сохраните новую копию Excel.").grid(
            row=1, column=0, columnspan=3, pady=(10, 0), sticky="w")
        ttk.Label(top, text="Партія = дата изготовления. Сохранение в новую копию Excel. Обработка локальная.").grid(
            row=2, column=0, columnspan=3, sticky="w")
        self.update_existing = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Обновлять строки с тем же номером протокола (пустые поля не стирают прежние значения)",
                        variable=self.update_existing).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        bar = ttk.Frame(root, padding=(12, 0, 12, 8))
        bar.grid(row=1, column=0, sticky="ew")
        ttk.Button(bar, text="Добавить DOCX / PDF…", command=self.add_files).pack(side="left")
        ttk.Button(bar, text="Удалить выбранный", command=self.remove).pack(side="left", padx=8)
        self.status = tk.StringVar(value="Документы ещё не выбраны")
        ttk.Label(bar, textvariable=self.status).pack(side="right")
        body = ttk.Panedwindow(root, orient="horizontal")
        body.grid(row=2, column=0, sticky="nsew", padx=12)
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=3)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(left, width=32, exportselection=False)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.bind("<<ListboxSelect>>", self.select)
        right.columnconfigure(1, weight=1)
        self.variables = {}
        for i, (col, label) in enumerate(FIELDS):
            ttk.Label(right, text=label + ":").grid(row=i, column=0, sticky="w", padx=(12, 10), pady=3)
            variable = tk.StringVar()
            self.variables[col] = variable
            if col in {"O", "P"}:
                widget = ttk.Combobox(right, textvariable=variable, state="readonly", values=("", "Відповідає", "Не відповідає"))
            else:
                widget = ttk.Entry(right, textvariable=variable)
            widget.grid(row=i, column=1, sticky="ew", pady=3)
            variable.trace_add("write", self.edited)
        ttk.Label(right, text="Даты: ДД.ММ.ГГГГ. Масса: кг. Постачальник / Виробник: коды ЄДРПОУ (8 цифр).",
                  wraplength=650).grid(row=13, column=0, columnspan=2, sticky="w", padx=12, pady=6)
        self.notes = tk.Text(right, height=9, wrap="word", state="disabled", background="#fff4d6")
        self.notes.grid(row=14, column=0, columnspan=2, sticky="nsew", padx=(12, 0))
        right.rowconfigure(14, weight=1)
        self.checked = tk.BooleanVar()
        ttk.Checkbutton(right, text="Я проверил(а) эту запись, предупреждения и пустые поля",
                        variable=self.checked, command=self.mark_reviewed).grid(row=15, column=0, columnspan=2, sticky="w", padx=12, pady=8)
        bottom = ttk.Frame(root, padding=12)
        bottom.grid(row=3, column=0, sticky="ew")
        ttk.Label(bottom, text="PDF, включая сканы: нужен Tesseract OCR. DOC: сохраните как DOCX.").pack(side="left")
        ttk.Button(bottom, text="Сохранить Excel…", command=self.save).pack(side="right")

    def choose_template(self):
        name = filedialog.askopenfilename(title="Выберите исходную таблицу", filetypes=[("Excel", "*.xlsx")])
        if name:
            self.template.set(name)

    def commit(self):
        if self.current is not None and self.current < len(self.records):
            self.records[self.current].values = {col: var.get().strip() for col, var in self.variables.items()}

    def edited(self, *_):
        if not self.loading and self.current is not None:
            self.reviewed.discard(self.current)
            self.checked.set(False)
            self.commit()
            self.update_notes()
            self.update_status()

    def update_status(self):
        self.status.set(f"Документов: {len(self.records)}; проверено: {len(self.reviewed)}")

    def update_notes(self):
        if self.current is None:
            text = "Выберите документ слева."
        else:
            record = self.records[self.current]
            text = "\n\n".join(record.warnings) or "Противоречий автоматически не найдено. Сверьте данные с документом."
            if record.missing():
                text += "\n\nПустые поля: " + ", ".join(record.missing())
            text += "\n\nПредупреждения описывают исходный документ и остаются в отчёте после исправления полей."
        self.notes.configure(state="normal")
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", text)
        self.notes.configure(state="disabled")

    def load_record(self, index):
        self.loading = True
        self.current = index
        for col, var in self.variables.items():
            var.set(self.records[index].values.get(col, "") if index is not None else "")
        self.checked.set(index in self.reviewed)
        self.loading = False
        self.update_notes()
        self.update_status()

    def select(self, _event=None):
        indexes = self.listbox.curselection()
        if not indexes:
            return
        self.commit()
        self.load_record(indexes[0])

    def mark_reviewed(self):
        if self.current is None:
            self.checked.set(False)
            return
        self.commit()
        if self.checked.get():
            try:
                validate(self.records[self.current])
            except ValueError as exc:
                self.checked.set(False)
                messagebox.showerror("Проверьте поле", str(exc))
                return
            self.reviewed.add(self.current)
        else:
            self.reviewed.discard(self.current)
        self.update_status()

    def add_files(self):
        if self.busy:
            return
        paths = filedialog.askopenfilenames(title="Выберите протоколы", filetypes=[("Протоколы", "*.docx *.pdf"), ("Word", "*.docx"), ("PDF", "*.pdf")])
        if not paths:
            return
        self.commit()
        self.busy = True
        self.root.configure(cursor="watch")
        events = Queue()

        def work():
            loaded, errors = [], []
            for path in paths:
                try:
                    events.put(("progress", f"Чтение: {Path(path).name}"))
                    record = extract(Path(path), progress=lambda text: events.put(("progress", text)))
                    loaded.append(record)
                except Exception as exc:
                    errors.append(f"{Path(path).name}: {exc}")
            events.put(("done", (loaded, errors)))

        def poll():
            try:
                while True:
                    kind, payload = events.get_nowait()
                    if kind == "progress":
                        self.status.set(payload)
                        continue
                    loaded, errors = payload
                    for record in loaded:
                        self.records.append(record)
                        self.listbox.insert("end", f'{record.values["D"]} | {record.source}')
                    self.busy = False
                    self.root.configure(cursor="")
                    if self.records and self.current is None:
                        self.listbox.selection_set(0)
                        self.load_record(0)
                    self.update_status()
                    if errors:
                        messagebox.showwarning("Не все документы прочитаны", "\n\n".join(errors))
                    return
            except Empty:
                self.root.after(100, poll)

        Thread(target=work, daemon=True).start()
        self.root.after(100, poll)

    def remove(self):
        if self.current is None:
            return
        index = self.current
        self.records.pop(index)
        self.listbox.delete(index)
        self.reviewed = {i if i < index else i - 1 for i in self.reviewed if i != index}
        self.current = None
        self.listbox.selection_clear(0, "end")
        if self.records:
            index = min(index, len(self.records) - 1)
            self.listbox.selection_set(index)
            self.load_record(index)
        else:
            self.load_record(None)

    def save(self):
        if self.busy:
            messagebox.showinfo("Идёт распознавание", "Дождитесь завершения чтения документов.")
            return
        self.commit()
        if not self.records:
            messagebox.showinfo("Нет документов", "Сначала добавьте протоколы.")
            return
        if len(self.reviewed) != len(self.records):
            messagebox.showinfo("Проверьте записи", "Выберите каждый документ, проверьте данные и поставьте отметку под предупреждениями.")
            return
        template = Path(self.template.get())
        if not template.is_file():
            messagebox.showerror("Не выбран Excel", "Выберите существующий файл .xlsx с вашей таблицей.")
            return
        output = filedialog.asksaveasfilename(title="Сохранить новую копию таблицы", initialfile="Заполненная_таблица.xlsx", defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if not output:
            return
        try:
            report = write_excel(template, Path(output), self.records, "update" if self.update_existing.get() else "skip")
        except Exception as exc:
            messagebox.showerror("Не удалось сохранить Excel", str(exc))
            return
        report_path = Path(output).with_suffix(".report.txt")
        try:
            with report_path.open("x", encoding="utf-8-sig") as stream:
                stream.write(report_text(report))
        except OSError as exc:
            messagebox.showwarning("Excel сохранён", f"Excel сохранён: {output}\nНе удалось записать отчёт: {exc}")
            return
        messagebox.showinfo("Готово", f'Добавлено строк: {len(report["added"])}\nОбновлено строк: {len(report["updated"])}\nПропущено дублей: {len(report["skipped"])}\n\nExcel: {output}\nОтчёт: {report_path}\n\nСверьте результат перед использованием.')


if __name__ == "__main__":
    App(tk.Tk()).root.mainloop()
