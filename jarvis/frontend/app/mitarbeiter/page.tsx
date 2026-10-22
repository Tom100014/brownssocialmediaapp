"use client";

import { useEffect, useState } from "react";
import {
  JarvisApiError,
  StaffBooking,
  StaffSummaryEntry,
  bookStaffConsumption,
  getStaffConsumptionFor,
  getStaffConsumptionSummary,
  hasConnection,
} from "@/lib/api";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function formatEuro(value: number): string {
  return value.toLocaleString("de-DE", { style: "currency", currency: "EUR" });
}

export default function StaffConsumptionPage() {
  const [date, setDate] = useState(todayIso());
  const [employees, setEmployees] = useState<StaffSummaryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<string | null>(null);
  const [selectedBookings, setSelectedBookings] = useState<StaffBooking[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  const [showForm, setShowForm] = useState(false);
  const [formEmployee, setFormEmployee] = useState("");
  const [formTable, setFormTable] = useState("");
  const [formItems, setFormItems] = useState("");
  const [formValue, setFormValue] = useState("");
  const [formDiscount, setFormDiscount] = useState("50");
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function loadSummary() {
    if (!hasConnection()) {
      setError("Nicht mit einem Jarvis-Server verbunden.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const summary = await getStaffConsumptionSummary(date);
      setEmployees(summary.employees);
    } catch (err) {
      setError(err instanceof JarvisApiError ? err.message : "Laden fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);

  async function openEmployee(name: string) {
    if (selected === name) {
      setSelected(null);
      return;
    }
    setSelected(name);
    setDetailLoading(true);
    try {
      const bookings = await getStaffConsumptionFor(name);
      setSelectedBookings(bookings.filter((b) => b.booking_date === date));
    } catch (err) {
      setError(err instanceof JarvisApiError ? err.message : "Laden fehlgeschlagen.");
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);

    const tableNumber = parseInt(formTable, 10);
    const fullValue = parseFloat(formValue.replace(",", "."));
    const discount = parseFloat(formDiscount.replace(",", "."));

    if (!formEmployee.trim()) return setFormError("Mitarbeitername fehlt.");
    if (!Number.isFinite(tableNumber)) return setFormError("Tischnummer ist ungültig.");
    if (!formItems.trim()) return setFormError("Artikel fehlen.");
    if (!Number.isFinite(fullValue) || fullValue < 0) return setFormError("Warenwert ist ungültig.");

    setSaving(true);
    try {
      await bookStaffConsumption({
        employee_name: formEmployee.trim(),
        table_number: tableNumber,
        items: formItems.trim(),
        full_value: fullValue,
        discount_percent: Number.isFinite(discount) ? discount : 50,
      });
      setFormEmployee("");
      setFormTable("");
      setFormItems("");
      setFormValue("");
      setFormDiscount("50");
      setShowForm(false);
      await loadSummary();
      if (selected) await openEmployee(selected);
    } catch (err) {
      setFormError(err instanceof JarvisApiError ? err.message : "Speichern fehlgeschlagen.");
    } finally {
      setSaving(false);
    }
  }

  const dayTotalSavings = employees.reduce((sum, e) => sum + e.total_savings, 0);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-5 px-4 py-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-white">Mitarbeiter-Verzehr</h1>
          <p className="text-xs text-white/40">Personal-Tische · 50% Mitarbeiterrabatt je Buchung</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="rounded-lg border border-jarvis-border bg-jarvis-panel2 px-3 py-1.5 text-sm text-white outline-none focus:border-jarvis-accent"
          />
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded-full bg-gradient-to-r from-jarvis-accent to-jarvis-accent2 px-4 py-1.5 text-sm font-semibold text-white"
          >
            + Buchung
          </button>
        </div>
      </header>

      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="grid grid-cols-2 gap-3 rounded-2xl border border-jarvis-border bg-jarvis-panel p-4 sm:grid-cols-3"
        >
          <div className="col-span-2 sm:col-span-1">
            <label className="mb-1 block text-xs text-white/50">Mitarbeiter</label>
            <input
              value={formEmployee}
              onChange={(e) => setFormEmployee(e.target.value)}
              placeholder="z. B. Emona"
              className="w-full rounded-lg border border-jarvis-border bg-jarvis-panel2 px-3 py-2 text-sm text-white outline-none focus:border-jarvis-accent"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-white/50">Tisch</label>
            <input
              value={formTable}
              onChange={(e) => setFormTable(e.target.value)}
              placeholder="1001"
              inputMode="numeric"
              className="w-full rounded-lg border border-jarvis-border bg-jarvis-panel2 px-3 py-2 text-sm text-white outline-none focus:border-jarvis-accent"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-white/50">Rabatt %</label>
            <input
              value={formDiscount}
              onChange={(e) => setFormDiscount(e.target.value)}
              className="w-full rounded-lg border border-jarvis-border bg-jarvis-panel2 px-3 py-2 text-sm text-white outline-none focus:border-jarvis-accent"
            />
          </div>
          <div className="col-span-2 sm:col-span-2">
            <label className="mb-1 block text-xs text-white/50">Artikel</label>
            <input
              value={formItems}
              onChange={(e) => setFormItems(e.target.value)}
              placeholder="1x Burger, 1x Cola"
              className="w-full rounded-lg border border-jarvis-border bg-jarvis-panel2 px-3 py-2 text-sm text-white outline-none focus:border-jarvis-accent"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-white/50">Warenwert €</label>
            <input
              value={formValue}
              onChange={(e) => setFormValue(e.target.value)}
              placeholder="13,82"
              inputMode="decimal"
              className="w-full rounded-lg border border-jarvis-border bg-jarvis-panel2 px-3 py-2 text-sm text-white outline-none focus:border-jarvis-accent"
            />
          </div>
          <div className="col-span-2 flex items-end gap-2 sm:col-span-3">
            <button
              type="submit"
              disabled={saving}
              className="rounded-full bg-gradient-to-r from-jarvis-accent to-jarvis-accent2 px-5 py-2 text-sm font-semibold text-white disabled:opacity-40"
            >
              {saving ? "Speichere..." : "Buchen"}
            </button>
            {formError && <p className="text-xs text-jarvis-err">{formError}</p>}
          </div>
        </form>
      )}

      {error && <p className="text-xs text-jarvis-err">{error}</p>}

      {!loading && employees.length > 0 && (
        <div className="rounded-xl border border-jarvis-border bg-jarvis-panel/60 px-4 py-3 text-xs text-white/50">
          Tagesersparnis gesamt ({employees.length} Mitarbeiter): <span className="text-jarvis-ok font-medium">{formatEuro(dayTotalSavings)}</span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {loading && <p className="col-span-full text-sm text-white/40">Lade...</p>}
        {!loading && employees.length === 0 && !error && (
          <p className="col-span-full text-sm text-white/40">Keine Buchungen für dieses Datum.</p>
        )}
        {employees.map((emp) => (
          <button
            key={emp.employee_name}
            onClick={() => openEmployee(emp.employee_name)}
            className={`flex flex-col items-start gap-1 rounded-2xl border p-4 text-left transition-colors ${
              selected === emp.employee_name
                ? "border-jarvis-accent bg-jarvis-accent/10"
                : "border-jarvis-border bg-jarvis-panel hover:border-jarvis-accent/50"
            }`}
          >
            <span className="text-sm font-semibold text-white">{emp.employee_name}</span>
            <span className="text-xs text-white/40">{emp.booking_count} Buchung(en)</span>
            <span className="mt-1 text-lg font-semibold text-jarvis-accent">{formatEuro(emp.total_staff_price)}</span>
            <span className="text-[11px] text-white/40">Ersparnis {formatEuro(emp.total_savings)}</span>
          </button>
        ))}
      </div>

      {selected && (
        <div className="rounded-2xl border border-jarvis-border bg-jarvis-panel p-4">
          <h2 className="mb-3 text-sm font-semibold text-white">Buchungen · {selected}</h2>
          {detailLoading && <p className="text-sm text-white/40">Lade...</p>}
          {!detailLoading && selectedBookings.length === 0 && (
            <p className="text-sm text-white/40">Keine Buchungen für dieses Datum.</p>
          )}
          <div className="space-y-2">
            {selectedBookings.map((b) => (
              <div
                key={b.id}
                className="flex items-center justify-between rounded-lg border border-jarvis-border bg-jarvis-panel2 px-3 py-2 text-sm"
              >
                <div>
                  <p className="text-white">Tisch {b.table_number} · {b.items}</p>
                  <p className="text-xs text-white/40">{new Date(b.created_at).toLocaleTimeString("de-DE")}</p>
                </div>
                <div className="text-right">
                  <p className="text-white/50 line-through">{formatEuro(b.full_value)}</p>
                  <p className="font-semibold text-jarvis-accent">{formatEuro(b.staff_price)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
