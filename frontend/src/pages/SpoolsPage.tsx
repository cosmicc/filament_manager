import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Boxes,
  CheckCircle2,
  Filter,
  MapPin,
  PackageMinus,
  Pencil,
  Plus,
  QrCode,
  Scale,
  Search,
  Star,
  Trash2,
} from "lucide-react";
import {
  type FormEvent,
  useEffect,
  useMemo,
  useState,
} from "react";
import { ApiClientError, apiFetch, idempotencyKey } from "../api/client";
import type { Filament, MaterialTemplate, Page, Printer, Spool } from "../api/types";
import { CollectionViewSelector } from "../components/CollectionViewSelector";
import { EditorSection } from "../components/EditorSection";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { Modal } from "../components/Modal";
import { MaterialTypeFilter } from "../components/MaterialTypeFilter";
import { InventoryChoiceSelect } from "../components/NewItemSelect";
import { DryingTemperatureDetails } from "../components/DryingTemperatureDetails";
import { SpoolTareSuggestions } from "../components/SpoolTareSuggestions";
import { PageHeader } from "../components/PageHeader";
import { StatusPill } from "../components/StatusPill";
import { useAuth } from "../context/AuthContext";
import { useRouter } from "../context/RouterContext";
import { useCollectionView } from "../hooks/useCollectionView";
import { filamentSwatchStyle } from "../lib/colors";
import { costPerGram, currencyAmount, dateTime, grams, inputNumber, percent } from "../lib/format";
import { materialIdentitySummary } from "../lib/materialIdentity";

function WeighModal({ spool, onClose }: { spool: Spool; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [grossMass, setGrossMass] = useState("");
  const [tareMass, setTareMass] = useState(
    Number(spool.tare_mass_g) > 0 ? inputNumber(spool.tare_mass_g, 1) : "",
  );
  const [notes, setNotes] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [override, setOverride] = useState(false);
  const [error, setError] = useState("");
  const net =
    grossMass && tareMass
      ? Math.max(0, Number(grossMass) - Number(tareMass))
      : null;

  const mutation = useMutation({
    mutationFn: () =>
      apiFetch(`/spools/${spool.id}/measurements`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey(`weigh-${spool.id}`) },
        body: JSON.stringify({
          gross_mass_g: grossMass,
          tare_mass_g: Number(spool.tare_mass_g) > 0 ? null : tareMass,
          source: "manual",
          confirmed,
          allow_above_nominal: override,
          notes: notes || null,
        }),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["spools"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
      onClose();
    },
    onError: (caught) => {
      if (
        caught instanceof ApiClientError &&
        caught.code === "measurement_confirmation_required"
      ) {
        setConfirmed(true);
        setError(
          "This is an increase from the expected amount. Review the values, then submit again to confirm the correction.",
        );
      } else
        setError(
          caught instanceof Error
            ? caught.message
            : "The measurement could not be saved",
        );
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    mutation.mutate();
  }

  return (
    <Modal
      title={`Weigh ${spool.spool_code}`}
      description={`${materialIdentitySummary(spool)}. Enter the complete spool weight; tare is deducted automatically.`}
      onClose={onClose}
      footer={
        <>
          <button className="button" onClick={onClose}>
            Cancel
          </button>
          <button
            className="button button--primary"
            form="weigh-form"
            disabled={mutation.isPending || !grossMass}
          >
            <Scale size={17} />
            {confirmed ? "Confirm measurement" : "Record measurement"}
          </button>
        </>
      }
    >
      <form
        id="weigh-form"
        className="form-stack"
        onSubmit={(event) => void submit(event)}
      >
        <div className="spool-identity-callout">
          <span
            className="filament-swatch"
            style={filamentSwatchStyle(spool.color_mode, spool.color_hexes, spool.color_hex ?? "2F80A5")}
          />
          <div>
            <strong>{materialIdentitySummary(spool)}</strong>
            <span>
              {spool.vendor_name ?? "Unspecified vendor"} · expected{" "}
              {grams(spool.remaining_mass_expected_g)}
            </span>
          </div>
        </div>
        <EditorSection
          title="Measurement"
          description="Enter the full spool weight; Filament Manager calculates remaining filament from the trusted tare."
        >
          <div className="form-stack">
            <label>
              Gross weight (grams)
              <div className="input-suffix">
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  inputMode="decimal"
                  value={grossMass}
                  onChange={(event) => setGrossMass(event.target.value)}
                  autoFocus
                  required
                />
                <span>g</span>
              </div>
            </label>
            {Number(spool.tare_mass_g) <= 0 && (
              <label>
                Verified empty-spool tare
                <div className="input-suffix">
                  <input
                    type="number"
                    min="0.1"
                    step="0.1"
                    inputMode="decimal"
                    value={tareMass}
                    onChange={(event) => setTareMass(event.target.value)}
                    required
                  />
                  <span>g</span>
                </div>
                <small className="field-help">
                  This establishes the previously unknown tare and is preserved
                  with the measurement.
                </small>
              </label>
            )}
            <div className="measurement-math">
              <span>
                <small>
                  {Number(spool.tare_mass_g) > 0 ? "Stored tare" : "New tare"}
                </small>
                <strong>{tareMass ? grams(tareMass, 1) : "—"}</strong>
              </span>
              <span className="math-symbol">−</span>
              <span>
                <small>Calculated filament</small>
                <strong>{net == null ? "—" : grams(net, 1)}</strong>
              </span>
            </div>
          </div>
        </EditorSection>
        <EditorSection
          title="Audit context"
          description="Record why the measurement or correction was made."
        >
          <div className="form-stack">
            <label>
              Notes <span className="label-optional">Optional</span>
              <textarea
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                rows={3}
                maxLength={4000}
                placeholder="Scale, reason for correction, or other context"
              />
            </label>
            {confirmed && (
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                <span>
                  <strong>Confirm unexpected increase</strong>
                  <small>
                    This preserves the correction in the audit trail.
                  </small>
                </span>
              </label>
            )}
            {user?.role === "administrator" &&
              net != null &&
              net > Number(spool.nominal_net_mass_g) && (
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={override}
                    onChange={(event) => setOverride(event.target.checked)}
                  />
                  <span>
                    <strong>Allow value above nominal capacity</strong>
                    <small>
                      Administrator override; use only after verifying the tare
                      and scale.
                    </small>
                  </span>
                </label>
              )}
          </div>
        </EditorSection>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}

function CreateSpoolModal({
  filaments,
  initialFilamentId,
  onClose,
}: {
  filaments: Filament[];
  initialFilamentId?: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const initialFilament = filaments.find((item) => item.id === initialFilamentId) ?? filaments[0];
  const [filamentId, setFilamentId] = useState(initialFilament?.id ?? "");
  const [filamentMass, setFilamentMass] = useState(
    inputNumber(initialFilament?.nominal_net_mass_g ?? "1000", 0),
  );
  const [fullSpoolMass, setFullSpoolMass] = useState("");
  const [knownTare, setKnownTare] = useState("");
  const [unusedSpool, setUnusedSpool] = useState(true);
  const [purchaseCost, setPurchaseCost] = useState("");
  const [error, setError] = useState("");
  const selected = filaments.find((item) => item.id === filamentId);
  const inferredTare =
    unusedSpool && fullSpoolMass && filamentMass
      ? Number(fullSpoolMass) - Number(filamentMass)
      : null;
  const mutation = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      if (!selected) throw new Error("Select a filament product");
      const data = new FormData(form);
      return apiFetch("/spools", {
        method: "POST",
        body: JSON.stringify({
          spool_code: String(data.get("spool_code")).trim(),
          filament_product_id: selected.id,
          nominal_net_mass_g: filamentMass,
          tare_mass_g: unusedSpool && fullSpoolMass.trim() ? null : knownTare.trim() || null,
          infer_tare_from_unused_spool: unusedSpool,
          initial_gross_mass_g:
            fullSpoolMass.trim() || null,
          purchase_source:
            String(data.get("purchase_source") ?? "").trim() || null,
          purchase_date: String(data.get("purchase_date") ?? "") || null,
          purchase_cost: purchaseCost.trim() || null,
          currency: "USD",
          location: String(data.get("location") ?? "").trim() || null,
          notes: String(data.get("notes") ?? "").trim() || null,
        }),
      });
    },
    onSuccess: async () => {
      // The POST has succeeded. Refresh failures belong to inventory queries,
      // not a save error that could prompt creation of a duplicate spool.
      onClose();
      await Promise.allSettled([
        queryClient.invalidateQueries({ queryKey: ["spools"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["spool-tare-suggestions"] }),
        queryClient.invalidateQueries({ queryKey: ["locations"] }),
        queryClient.invalidateQueries({ queryKey: ["spool-location-choices"] }),
      ]);
    },
    onError: (caught) =>
      setError(
        caught instanceof Error
          ? caught.message
          : "The spool could not be created",
      ),
  });
  return (
    <Modal
      title="Add a physical spool"
      description="Choose the filament, enter how much filament is on the new spool, and optionally enter its full scale weight."
      onClose={onClose}
      footer={
        <>
          <button className="button" onClick={onClose}>
            Cancel
          </button>
          <button
            className="button button--primary"
            form="create-spool-form"
            disabled={mutation.isPending || !selected}
          >
            <Plus size={17} />
            {mutation.isPending ? "Creating…" : "Create spool"}
          </button>
        </>
      }
    >
      <form
        id="create-spool-form"
        className="form-stack"
        onSubmit={(event) => {
          event.preventDefault();
          setError("");
          mutation.mutate(event.currentTarget);
        }}
      >
        <EditorSection
          title="Spool identity"
          description="Connect the physical label to its canonical filament product."
        >
          <div className="form-grid">
            <label className="form-grid__wide">
              Filament product
              <select
                value={filamentId}
                onChange={(event) => {
                  const nextId = event.target.value;
                  setFilamentId(nextId);
                  setKnownTare("");
                  const nextFilament = filaments.find((item) => item.id === nextId);
                  if (nextFilament) setFilamentMass(inputNumber(nextFilament.nominal_net_mass_g, 0));
                }}
                required
                autoFocus
              >
                {filaments.map((filament) => (
                  <option key={filament.id} value={filament.id}>
                    {filament.vendor_name ?? "Unspecified"} ·{" "}
                    {materialIdentitySummary(filament)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Spool code
              <input
                name="spool_code"
                pattern={'[A-Za-z0-9_\\-]+'}
                maxLength={64}
                placeholder="SPOOL-001"
                required
              />
            </label>
            <label>
              Location
            <InventoryChoiceSelect kind="location" name="location" />
            </label>
          </div>
        </EditorSection>
        <EditorSection
          title="Starting weight"
          description="The filament amount starts inventory tracking. A full-spool scale weight lets Filament Manager calculate the empty-spool weight automatically."
        >
          <div className="form-grid">
            <label className="check-row form-grid__wide"><input type="checkbox" checked={unusedSpool} onChange={(event) => setUnusedSpool(event.target.checked)} /><span>This spool is unused<small>Only an unused spool can infer tare from total scale weight minus purchased filament weight.</small></span></label>
            <label>
              Filament purchase weight (g)
              <input
                type="number"
                min="0.1"
                step="0.1"
                value={filamentMass}
                onChange={(event) => setFilamentMass(event.target.value)}
                required
              />
              <small className="field-help">
                Usually 1000 g for a new 1 kg spool. This is filament only, without the plastic spool.
              </small>
            </label>
            <label>
              Full spool scale weight (g) <span className="label-optional">Optional</span>
              <input
                type="number"
                min="0"
                step="0.1"
                value={fullSpoolMass}
                onChange={(event) => setFullSpoolMass(event.target.value)}
              />
              <small className="field-help">The scale reading with the filament and physical spool together.</small>
            </label>
          </div>
          {inferredTare !== null ? (
            inferredTare >= 0 ? (
              <p className="security-note">
                Calculated empty-spool weight: {grams(String(inferredTare), 1)} ({grams(fullSpoolMass, 1)} total minus {grams(filamentMass, 1)} filament).
              </p>
            ) : (
              <p className="form-error" role="alert">Full spool weight must be at least the entered filament amount.</p>
            )
          ) : null}
          <div className="form-grid">
            <label>Empty spool weight (g) <span className="label-optional">Optional</span>
              <input type="number" min="0" step="0.1" value={inferredTare !== null ? inputNumber(inferredTare, 1) : knownTare}
                readOnly={inferredTare !== null} onChange={(event) => setKnownTare(event.target.value)} />
              <small className="field-help">For an unused spool, total scale weight minus purchased filament gives the tare. For a used spool, enter a known or estimated tare; it can be corrected later.</small>
            </label>
            <SpoolTareSuggestions filamentId={filamentId} disabled={unusedSpool && Boolean(fullSpoolMass.trim())} onApply={setKnownTare} />
          </div>
        </EditorSection>
        <EditorSection
          title="Purchase and notes"
          description="Optional acquisition details and operator context."
        >
          <div className="form-grid">
            <label>
              Purchase source
              <input name="purchase_source" maxLength={160} />
            </label>
            <label>
              Purchase date
              <input name="purchase_date" type="date" />
            </label>
            <label>
              Purchase cost
              <input name="purchase_cost" type="number" min="0" step="0.01" value={purchaseCost} onChange={(event) => setPurchaseCost(event.target.value)} />
              <small className="field-help">
                {purchaseCost && filamentMass
                  ? `${costPerGram(Number(purchaseCost) / Number(filamentMass), 'USD')} using filament weight only.`
                  : "Enter the total price paid; the physical spool weight is excluded."}
              </small>
            </label>
            <label className="form-grid__wide">
              Notes <span className="label-optional">Optional</span>
              <textarea name="notes" rows={2} maxLength={4000} />
            </label>
          </div>
        </EditorSection>
        {selected && (
          <p className="muted">
            The selected filament defaults to {grams(selected.nominal_net_mass_g)}. You may correct the amount for this physical spool before saving. It will be projected to Spoolman automatically.
          </p>
        )}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}

function EditSpoolModal({
  spool,
  filaments,
  onClose,
  onSaved,
  onDeleted,
}: {
  spool: Spool;
  filaments: Filament[];
  onClose: () => void;
  onSaved: (updated: Spool) => void;
  onDeleted: (disposition: string) => void;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const [purchaseWeight, setPurchaseWeight] = useState(inputNumber(spool.nominal_net_mass_g, 1));
  const [purchaseCost, setPurchaseCost] = useState(spool.purchase_cost ?? "");
  const [currencyCode, setCurrencyCode] = useState(spool.currency);
  const [filamentId, setFilamentId] = useState(spool.filament_product_id);
  const [tare, setTare] = useState(inputNumber(spool.tare_mass_g, 1));
  const [tareEdited, setTareEdited] = useState(false);
  const effectiveTare = tareEdited ? Number(tare) : Number(spool.tare_mass_g);
  const updateTare = (value: string) => { setTare(value); setTareEdited(true); };
  const [remainingOverride, setRemainingOverride] = useState<string | null>(null);
  const basis = useQuery({
    queryKey: ["spool-mass-basis", spool.id, spool.record_version],
    queryFn: () => apiFetch<{ last_gross_mass_g: string | null; adjustment_since_weighing_g: string | null }>(`/spools/${spool.id}/mass-basis`),
  });
  const calculatedRemaining = basis.data?.last_gross_mass_g != null
    ? Math.max(0, Number(basis.data.last_gross_mass_g) - effectiveTare + Number(basis.data.adjustment_since_weighing_g ?? 0))
    : Number(spool.remaining_mass_effective_g);
  const remaining = remainingOverride === null ? calculatedRemaining : Number(remainingOverride);
  const mutation = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form);
      const payload: Record<string, unknown> = {
        expected_version: spool.record_version,
        spool_code: String(data.get("spool_code")).trim(),
        filament_product_id: String(data.get("filament_product_id")),
        nominal_net_mass_g: purchaseWeight === inputNumber(spool.nominal_net_mass_g, 1) ? spool.nominal_net_mass_g : purchaseWeight,
        tare_mass_g: tareEdited ? tare : spool.tare_mass_g,
        location: String(data.get("location") ?? "").trim() || null,
        purchase_source: String(data.get("purchase_source") ?? "").trim() || null,
        purchase_date: String(data.get("purchase_date") ?? "") || null,
        purchase_cost: String(data.get("purchase_cost") ?? "").trim() || null,
        currency: String(data.get("currency")),
        notes: String(data.get("notes") ?? "").trim() || null,
        archived: data.get("archived") === "on",
      };
      if (remainingOverride !== null) {
        payload.remaining_mass_g = remainingOverride;
      }
      return apiFetch<Spool>(`/spools/${spool.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: async (updated) => {
      onSaved(updated);
      await Promise.allSettled([
        queryClient.invalidateQueries({ queryKey: ["spools"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["spool-tare-suggestions"] }),
        queryClient.invalidateQueries({ queryKey: ["spool-mass-basis", spool.id] }),
        queryClient.invalidateQueries({ queryKey: ["locations"] }),
        queryClient.invalidateQueries({ queryKey: ["spool-location-choices"] }),
      ]);
    },
    onError: (caught) =>
      setError(
        caught instanceof Error
          ? caught.message
          : "The spool could not be saved",
      ),
  });
  const remove = useMutation({
    mutationFn: () => apiFetch<{ disposition: string }>(`/spools/${spool.id}`, { method: "DELETE" }),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["spools"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
      onDeleted(result.disposition);
    },
    onError: (caught) => setError(caught instanceof Error ? caught.message : "The spool could not be removed"),
  });

  return (
    <Modal
      title={`Edit ${spool.spool_code}`}
      description={`${materialIdentitySummary(spool)}. Correct any setup field; remaining-mass corrections are retained as immutable adjustment history.`}
      onClose={onClose}
      size="wide"
      footer={
        <>
          <button
            className="button button--danger"
            type="button"
            disabled={remove.isPending || mutation.isPending}
            onClick={() => {
              if (window.confirm(`Remove ${spool.spool_code}? It will be archived instead if retained history prevents safe deletion.`)) remove.mutate();
            }}
          >
            <Trash2 size={17} /> {remove.isPending ? "Removing…" : "Delete or archive"}
          </button>
          <button className="button" onClick={onClose}>
            Cancel
          </button>
          <button
            className="button button--primary"
            form="edit-spool-form"
            disabled={mutation.isPending || remove.isPending || basis.isPending || basis.isError}
          >
            <Pencil size={17} />
            {mutation.isPending ? "Saving…" : "Save spool"}
          </button>
        </>
      }
    >
      <form
        id="edit-spool-form"
        className="editor-form"
        onSubmit={(event) => {
          event.preventDefault();
          setError("");
          mutation.mutate(event.currentTarget);
        }}
      >
        <EditorSection
          title="Identity and filament"
          description="Correct the physical label, linked filament, capacity, tare, or current remaining amount."
        >
          <div className="form-grid">
            <label>Spool code<input name="spool_code" defaultValue={spool.spool_code} pattern={'[A-Za-z0-9_\\-]+'} maxLength={64} required autoFocus /></label>
            <label>Filament product<select name="filament_product_id" value={filamentId} onChange={(event) => setFilamentId(event.target.value)} required>{filaments.map((filament) => <option key={filament.id} value={filament.id}>{filament.vendor_name ?? 'Unspecified'} · {materialIdentitySummary(filament)}</option>)}</select></label>
            <label>Filament purchase weight (g)<input name="nominal_net_mass_g" type="number" min="0.1" step="0.1" value={purchaseWeight} onChange={(event) => setPurchaseWeight(event.target.value)} required /><small className="field-help">Net filament purchased, excluding the empty physical spool.</small></label>
            <label>Empty spool weight (g)<input name="tare_mass_g" type="number" min="0" step="0.1" value={tare} onChange={(event) => updateTare(event.target.value)} required /><small className="field-help">Changing tare automatically recalculates remaining filament from the last scale weight and subsequent usage.</small></label>
            <label>Current filament remaining (g)<input name="remaining_mass_g" type="number" min="0" step="0.1" value={remainingOverride ?? inputNumber(calculatedRemaining, 1)} onChange={(event) => setRemainingOverride(event.target.value)} required /><small className="field-help">Calculated automatically. Typing a value records an explicit operator correction.</small>{remainingOverride !== null ? <button type="button" className="text-button" onClick={() => setRemainingOverride(null)}>Use calculated remaining</button> : null}</label>
            <label>Current total spool weight (g)<input value={inputNumber(remaining + effectiveTare, 1)} readOnly aria-readonly="true" /><small className="field-help">Remaining filament + empty spool weight.{effectiveTare <= 0 ? ' Tare is not yet known.' : ''}</small></label>
          <label>Location<InventoryChoiceSelect kind="location" name="location" defaultValue={spool.location ?? ''} /></label>
            <SpoolTareSuggestions filamentId={filamentId} onApply={updateTare} />
          </div>
          {basis.data ? <p className="field-help">{basis.data.last_gross_mass_g === null ? 'No retained scale reading: the existing purchase/usage estimate is preserved until you weigh this spool.' : `Last scale weight: ${grams(basis.data.last_gross_mass_g, 1)}. Subsequent usage and adjustments: ${grams(basis.data.adjustment_since_weighing_g ?? '0', 1)}. Original weigh-in history is never overwritten.`}</p> : null}
          {basis.isError ? <p className="form-error" role="alert">Weight evidence could not be loaded. Close and reopen this editor before saving.</p> : null}
          <p className="security-note">
            <MapPin size={16} /> Filament Manager remains authoritative and will project these corrections to Spoolman.
          </p>
        </EditorSection>
        <EditorSection title="Purchase and lifecycle" description="Correct acquisition details, notes, or archive state.">
          <div className="form-grid">
            <label>Purchase source<input name="purchase_source" defaultValue={spool.purchase_source ?? ''} maxLength={160} /></label>
            <label>Purchase date<input name="purchase_date" type="date" defaultValue={spool.purchase_date ?? ''} /></label>
            <label>Purchase cost<input name="purchase_cost" type="number" min="0" step="0.01" value={purchaseCost} onChange={(event) => setPurchaseCost(event.target.value)} /><small className="field-help">{purchaseCost && purchaseWeight ? `${costPerGram(Number(purchaseCost) / Number(purchaseWeight), currencyCode)} based on purchase cost ÷ net filament weight.` : 'Enter cost and net filament weight to calculate cost per gram.'}</small></label>
            <label>Currency<input name="currency" pattern="[A-Z]{3}" maxLength={3} value={currencyCode} onChange={(event) => setCurrencyCode(event.target.value.toUpperCase())} required /></label>
            <label className="form-grid__wide">Notes<textarea name="notes" rows={3} maxLength={4000} defaultValue={spool.notes ?? ''} /></label>
            <label className="check-row form-grid__wide"><input name="archived" type="checkbox" defaultChecked={spool.archived} /><span><strong>Archive this spool</strong><small>Archived spools are retained for history and hidden from normal inventory.</small></span></label>
          </div>
        </EditorSection>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}

export default function SpoolsPage() {
  const { user } = useAuth();
  const { navigate } = useRouter();
  const queryClient = useQueryClient();
  const creationRequest = new URLSearchParams(window.location.search);
  const requestedFilamentId = creationRequest.get("filament_id") ?? undefined;
  const canEdit = user?.role !== "viewer";
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [material, setMaterial] = useState("");
  const [view, setView] = useCollectionView("spools", "list");
  const [selected, setSelected] = useState<Spool | null>(null);
  const [requestedSpoolId, setRequestedSpoolId] = useState(creationRequest.get("spool_id"));
  const requestedSpool = useQuery({
    queryKey: ["spools", "detail", requestedSpoolId],
    queryFn: () => apiFetch<Spool>(`/spools/${encodeURIComponent(requestedSpoolId ?? '')}`),
    enabled: Boolean(requestedSpoolId),
  });
  useEffect(() => {
    if (requestedSpool.data && requestedSpoolId) {
      setSelected(requestedSpool.data);
      setRequestedSpoolId(null);
      navigate("/spools", true);
    }
  }, [navigate, requestedSpool.data, requestedSpoolId]);
  const [weighing, setWeighing] = useState<Spool | null>(null);
  const [editingSpool, setEditingSpool] = useState<Spool | null>(null);
  const [creating, setCreating] = useState(creationRequest.get("create") === "1");
  const [actionError, setActionError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const query = useQuery({
    queryKey: ["spools", search, status, material],
    queryFn: () =>
      apiFetch<Page<Spool>>(
        `/spools?limit=200${search ? `&search=${encodeURIComponent(search)}` : ""}${status ? `&status=${encodeURIComponent(status)}` : ""}${material ? `&material=${encodeURIComponent(material)}` : ""}`,
      ),
    refetchInterval: 15_000,
  });
  const filaments = useQuery({
    queryKey: ["filaments"],
    queryFn: () => apiFetch<Filament[]>("/filaments"),
  });
  const templates = useQuery({
    queryKey: ["material-templates"],
    queryFn: () => apiFetch<MaterialTemplate[]>("/profiles/templates"),
  });
  const printers = useQuery({
    queryKey: ["printers"],
    queryFn: () => apiFetch<Printer[]>("/printers"),
    refetchInterval: 15_000,
  });
  const printerNames = useMemo(
    () =>
      new Map(
        (printers.data ?? []).map((printer) => [printer.id, printer.name]),
      ),
    [printers.data],
  );
  const items = useMemo(() => query.data?.items ?? [], [query.data?.items]);
  useEffect(() => {
    if (!selected) return;
    const current = items.find((spool) => spool.id === selected.id);
    if (current && current !== selected) setSelected(current);
  }, [items, selected]);
  useEffect(() => {
    setActionError("");
    setActionMessage("");
  }, [selected?.id]);
  const requestLoad = useMutation({
    mutationFn: (spool: Spool) =>
      apiFetch(`/spools/${spool.id}/set-active`, { method: "POST" }),
    onSuccess: async () => {
      setActionError("");
      setActionMessage(
        "Load request sent to Fluidd. Spoolman will update after the physical load finishes.",
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["spools"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
    onError: (caught) => {
      setActionMessage("");
      setActionError(
        caught instanceof Error
          ? caught.message
          : "Could not request the spool change",
      );
    },
  });
  const requestUnload = useMutation({
    mutationFn: () =>
      apiFetch("/printer-context/active-spool/clear", { method: "POST" }),
    onSuccess: async () => {
      setActionError("");
      setActionMessage(
        "Unload request sent to Fluidd. The active Spoolman spool clears after the physical unload finishes.",
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["spools"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
    onError: (caught) => {
      setActionMessage("");
      setActionError(
        caught instanceof Error
          ? caught.message
          : "Could not request the spool unload",
      );
    },
  });
  const needsAttention = useMemo(
    () =>
      items.filter(
        (spool) => spool.status === "needs_weighing" || spool.status === "low",
      ).length,
    [items],
  );

  return (
    <div>
      <PageHeader
        eyebrow="Physical inventory"
        title="Spools"
        description="Track each labeled spool, its trustworthy remaining mass, and its projection state."
        actions={
          canEdit ? (
            <button
              className="button button--primary"
              onClick={() => setCreating(true)}
              disabled={!filaments.data?.length}
            >
              <Plus size={17} /> Add spool
            </button>
          ) : undefined
        }
      />
      <section className="toolbar">
        <label className="search-field">
          <Search size={18} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search code, material, color, filler, finish, or location"
            aria-label="Search spools"
          />
        </label>
        <MaterialTypeFilter templates={templates.data ?? []} value={material} onChange={setMaterial} />
        <label className="select-field">
          <Filter size={17} />
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            aria-label="Filter by status"
          >
            <option value="">All statuses</option>
            <option value="needs_weighing">Needs weighing</option>
            <option value="in_stock">In stock</option>
            <option value="low">Low</option>
            <option value="empty">Empty</option>
          </select>
        </label>
        <CollectionViewSelector label="Spools" value={view} onChange={setView} />
        <span className="toolbar__summary">
          {query.data?.total ?? 0} spools · {needsAttention} need attention
        </span>
      </section>

      {requestedSpool.isError ? <p className="form-error" role="alert">The selected spool could not be loaded.</p> : null}
      {query.isError ? <p className="form-error" role="alert">Spools could not be loaded. Please retry.</p> : query.isLoading ? (
        <LoadingState label="Loading spools" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Boxes}
          title="No spools found"
          description="Adjust the filters or import the master workbook to establish inventory."
        />
      ) : view === "list" ? (
          <div className="table-card collection-table">
            <table>
              <thead>
                <tr>
                  <th>Spool</th>
                  <th>Material</th>
                  <th>Remaining</th>
                  <th>Cost / gram</th>
                  <th>Status</th>
                  <th>Prints</th>
                  <th>Location</th>
                  <th>Last weighed</th>
                </tr>
              </thead>
              <tbody>
                {items.map((spool) => (
                  <tr
                    key={spool.id}
                    onClick={() => setSelected(spool)}
                    tabIndex={0}
                    onKeyDown={(event) =>
                      (event.key === "Enter" || event.key === " ") && setSelected(spool)
                    }
                  >
                    <td>
                      <div className="table-identity">
                        <span
                          className="filament-swatch"
                          style={filamentSwatchStyle(spool.color_mode, spool.color_hexes, spool.color_hex ?? "2F80A5")}
                        />
                        <span>
                          <strong>{spool.spool_code}</strong>
                          <small>{spool.vendor_name ?? "No vendor"}</small>
                        </span>
                      </div>
                    </td>
                    <td>
                      <strong>{materialIdentitySummary(spool)}</strong>
                    </td>
                    <td>
                      <div className="table-progress">
                        <span>
                          <strong>
                            {grams(spool.remaining_mass_effective_g)}
                          </strong>
                          <small>{percent(spool.remaining_percent)}</small>
                        </span>
                        <div className="progress progress--small">
                          <span
                            style={{
                              width: `${Math.min(100, Number(spool.remaining_percent))}%`,
                            }}
                          />
                        </div>
                      </div>
                    </td>
                    <td>{costPerGram(spool.cost_per_gram, spool.currency)}</td>
                    <td>
                      <div className="status-stack">
                        {spool.active_printer_id ? (
                          <StatusPill status="active" />
                        ) : null}
                        <StatusPill status={spool.status} />
                      </div>
                    </td>
                    <td>{spool.completed_print_count.toLocaleString()}</td>
                    <td>{spool.location ?? "—"}</td>
                    <td>{dateTime(spool.last_measurement_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      ) : (
        <section className={`collection-grid collection-grid--${view}`}>
          {items.map((spool) => <button className={`collection-card collection-card--button${view === "detailed" ? " collection-card--detailed" : ""}`} key={spool.id} onClick={() => setSelected(spool)}>
            <header className="collection-card__header">
              <div className="table-identity"><span className={`filament-swatch${view === "detailed" ? " filament-swatch--large" : ""}`} style={filamentSwatchStyle(spool.color_mode, spool.color_hexes, spool.color_hex ?? "2F80A5")} /><span><strong>{spool.spool_code}</strong><small>{spool.vendor_name ?? "No vendor"}</small></span></div>
              <span className="status-stack">{spool.active_printer_id ? <StatusPill status="active" /> : null}<StatusPill status={spool.status} /></span>
            </header>
            <div className="collection-card__body"><h2>{materialIdentitySummary(spool)}</h2><div className="table-progress"><span><strong>{grams(spool.remaining_mass_effective_g)}</strong><small>{percent(spool.remaining_percent)}</small></span><div className="progress progress--small"><span style={{ width: `${Math.min(100, Number(spool.remaining_percent))}%` }} /></div></div></div>
            <dl className="catalog-meta"><div><dt>Cost / gram</dt><dd>{costPerGram(spool.cost_per_gram, spool.currency)}</dd></div><div><dt>Location</dt><dd>{spool.location ?? "Not set"}</dd></div>{view === "detailed" ? <><div><dt>Completed prints</dt><dd>{spool.completed_print_count.toLocaleString()}</dd></div><div><dt>Last weighed</dt><dd>{dateTime(spool.last_measurement_at)}</dd></div><div><dt>Confidence</dt><dd>{spool.weight_confidence}</dd></div><div><dt>Printer</dt><dd>{spool.active_printer_id ? printerNames.get(spool.active_printer_id) ?? "Assigned printer" : "Not active"}</dd></div></> : null}</dl>
            <span className="collection-card__link">Open details and actions</span>
          </button>)}
        </section>
      )}

      {selected ? <Modal title={`${selected.spool_code} details`} description={`${materialIdentitySummary(selected)}. Inspect this spool and use the same inventory actions from any catalog view.`} size="wide" onClose={() => setSelected(null)} footer={<button className="button button--primary" onClick={() => setSelected(null)}>Done</button>}>
                <header className="collection-detail-heading">
                  <div className="table-identity">
                    <span
                      className="filament-swatch filament-swatch--large"
                      style={filamentSwatchStyle(selected.color_mode, selected.color_hexes, selected.color_hex ?? "2F80A5")}
                    />
                    <span>
                      <p className="eyebrow">Physical spool</p>
                      <h2>{selected.spool_code}</h2>
                      <small>{materialIdentitySummary(selected)}</small>
                    </span>
                  </div>
                  <StatusPill
                    status={
                      selected.active_printer_id ? "active" : selected.status
                    }
                  />
                </header>
                <div>
                  <dl className="definition-list">
                    <DryingTemperatureDetails filamentId={selected.filament_product_id} />
                    <div>
                      <dt>Filament</dt>
                      <dd>
                        {selected.vendor_name ?? "Unspecified vendor"} ·{" "}
                        {materialIdentitySummary(selected)}
                      </dd>
                    </div>
                    <div>
                      <dt>Remaining</dt>
                      <dd>
                        {grams(selected.remaining_mass_effective_g)} /{" "}
                        {grams(selected.nominal_net_mass_g)}
                      </dd>
                    </div>
                    <div>
                      <dt>Confidence</dt>
                      <dd>{selected.weight_confidence}</dd>
                    </div>
                    <div>
                      <dt>Tare mass</dt>
                      <dd>
                        {Number(selected.tare_mass_g) > 0
                          ? grams(selected.tare_mass_g, 1)
                          : "Unknown"}
                      </dd>
                    </div>
                    <div><dt>Current total spool weight</dt><dd>{grams(Number(selected.remaining_mass_effective_g) + Number(selected.tare_mass_g), 1)}{Number(selected.tare_mass_g) <= 0 ? ' (tare unknown)' : ''}</dd></div>
                    <div>
                      <dt>Purchase weight</dt>
                      <dd>{grams(selected.nominal_net_mass_g, 1)} filament only</dd>
                    </div>
                    <div>
                      <dt>Purchase cost</dt>
                      <dd>{currencyAmount(selected.purchase_cost, selected.currency)}</dd>
                    </div>
                    <div>
                      <dt>Cost per gram</dt>
                      <dd>{costPerGram(selected.cost_per_gram, selected.currency)}</dd>
                    </div>
                    <div>
                      <dt>Spoolman</dt>
                      <dd>
                        {selected.spoolman_id
                          ? `ID ${selected.spoolman_id}`
                          : "Projection pending"}
                      </dd>
                    </div>
                    <div>
                      <dt>Printer assignment</dt>
                      <dd>
                        {selected.active_printer_id
                          ? `Loaded in ${printerNames.get(selected.active_printer_id) ?? "assigned printer"}`
                          : "Not active"}
                      </dd>
                    </div>
                    <div>
                      <dt>Location</dt>
                      <dd>{selected.location || "Not set"}</dd>
                    </div>
                    <div>
                      <dt>Completed prints</dt>
                      <dd>{selected.completed_print_count.toLocaleString()}</dd>
                    </div>
                  </dl>
                  <div className="detail-actions">
                    {canEdit && (
                      <button
                        className="button button--primary"
                        onClick={() => { setWeighing(selected); setSelected(null); }}
                      >
                        <Scale size={17} /> Weigh spool
                      </button>
                    )}
                    {canEdit && (
                      <button
                        className="button"
                        onClick={() => { setEditingSpool(selected); setSelected(null); }}
                      >
                        <Pencil size={17} /> Edit spool
                      </button>
                    )}
                    {canEdit && selected.active_printer_id ? (
                      <button
                        className="button"
                        disabled={requestUnload.isPending}
                        onClick={() => requestUnload.mutate()}
                      >
                        <PackageMinus size={17} /> Unload and clear active spool
                      </button>
                    ) : null}
                    {canEdit && (
                      <button
                        className="button"
                        disabled={
                          !selected.spoolman_id ||
                          requestLoad.isPending ||
                          Boolean(selected.active_printer_id)
                        }
                        title={
                          !selected.spoolman_id
                            ? "Project this spool to Spoolman first"
                            : selected.active_printer_id
                              ? "This spool is already physically loaded"
                              : "Open the confirmed load workflow in Fluidd"
                        }
                        onClick={() => requestLoad.mutate(selected)}
                      >
                        <Star size={17} />
                        {selected.active_printer_id
                          ? "Active spool"
                          : "Load spool"}
                      </button>
                    )}
                    <a
                      className="button"
                      href={`/api/v1/spools/${selected.id}/label`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <QrCode size={17} /> View label
                    </a>
                  </div>
                  {actionError && (
                    <p className="form-error" role="alert">
                      {actionError}
                    </p>
                  )}
                  {actionMessage && (
                    <p className="success-note">
                      <CheckCircle2 size={17} /> {actionMessage}
                    </p>
                  )}
                  {selected.weight_confidence === "measured" && (
                    <p className="success-note">
                      <CheckCircle2 size={17} /> Physical measurement is the
                      trusted remaining value.
                    </p>
                  )}
                </div>
      </Modal> : null}
      {weighing && (
        <WeighModal
          spool={weighing}
          onClose={() => {
            setWeighing(null);
            setSelected(null);
          }}
        />
      )}
      {editingSpool && (
        <EditSpoolModal
          spool={editingSpool}
          filaments={filaments.data ?? []}
          onClose={() => setEditingSpool(null)}
          onSaved={(updated) => {
            setSelected(updated);
            setEditingSpool(null);
            setActionMessage("Spool corrections saved and queued for Spoolman.");
          }}
          onDeleted={(disposition) => {
            setSelected(null);
            setEditingSpool(null);
            setActionMessage(
              disposition === "deleted"
                ? "Unused spool deleted."
                : "Spool has retained history, so it was archived.",
            );
          }}
        />
      )}
      {creating && filaments.data && (
        <CreateSpoolModal
          filaments={filaments.data}
          initialFilamentId={requestedFilamentId}
          onClose={() => {
            setCreating(false);
            if (creationRequest.get("create") === "1") navigate("/spools", true);
          }}
        />
      )}
    </div>
  );
}
