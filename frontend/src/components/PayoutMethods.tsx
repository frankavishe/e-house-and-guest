"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError, type Schemas } from "@/lib/api/client";
import type { PayoutMethod } from "@/lib/api/owner";
import { formatPhone } from "@/lib/format";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";
import { Select } from "./ui/Select";

type Kind = PayoutMethod["kind"];
type Network = NonNullable<PayoutMethod["network"]>;
const NETWORKS: Network[] = ["mpesa", "mixx", "airtel", "halopesa", "azampesa"];

/** Where payouts go (FR-024): mobile money or bank, one default. */
export function PayoutMethods({ methods }: { methods: PayoutMethod[] }) {
  const t = useTranslations();
  const router = useRouter();
  const [adding, setAdding] = useState(methods.length === 0);
  const [kind, setKind] = useState<Kind>("mobile_money");
  const [network, setNetwork] = useState<Network>("mpesa");
  const [msisdn, setMsisdn] = useState("");
  const [bankName, setBankName] = useState("");
  const [accountName, setAccountName] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function request(key: string, send: () => Promise<{ error?: unknown }>, done?: () => void) {
    setBusy(key);
    setError(null);
    try {
      const { error: err } = await send();
      if (err) setError(apiError(err)?.message ?? t("errors.generic"));
      else {
        done?.();
        router.refresh();
      }
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(null);
    }
  }

  function add(e: FormEvent) {
    e.preventDefault();
    const mobile = kind === "mobile_money";
    const body: Schemas["PayoutMethodIn"] = {
      kind,
      account_name: accountName.trim(),
      network: mobile ? network : null,
      msisdn: mobile ? msisdn.trim() : null,
      bank_name: mobile ? null : bankName.trim(),
      account_number: mobile ? null : accountNumber.trim(),
      is_default: true,
    };
    void request(
      "add",
      () => api.POST("/api/v1/owner-profile/payout-methods", { body }),
      () => {
        setAdding(false);
        setMsisdn("");
        setAccountNumber("");
      },
    );
  }

  function remove(id: string) {
    void request(id, () =>
      api.DELETE("/api/v1/owner-profile/payout-methods/{method_id}", {
        params: { path: { method_id: id } },
      }),
    );
  }

  return (
    <section aria-labelledby="payout-methods" className="flex flex-col gap-3">
      <h2 id="payout-methods" className="text-lg font-semibold text-ink">
        {t("earnings.methods")}
      </h2>
      {methods.length === 0 && (
        <p className="rounded-2xl bg-warning-soft p-3 text-sm text-warning">
          {t("earnings.noMethod")}
        </p>
      )}
      <ul className="flex flex-col gap-2">
        {methods.map((m) => (
          <li
            key={m.id}
            className="flex items-center justify-between gap-3 rounded-3xl bg-card p-3"
          >
            <div className="flex min-w-0 flex-col">
              <span className="flex items-center gap-2 font-medium text-ink">
                {m.kind === "mobile_money" && m.network ? t(`networks.${m.network}`) : m.bank_name}
                {m.is_default && <Badge tone="brand">{t("earnings.default")}</Badge>}
              </span>
              <span className="truncate text-sm text-muted">
                {m.account_name} · {m.msisdn ? formatPhone(m.msisdn) : m.account_number_masked}
              </span>
            </div>
            <Button
              variant="ghost"
              className="shrink-0 text-danger"
              loading={busy === m.id}
              onClick={() => remove(m.id)}
            >
              {t("earnings.remove")}
            </Button>
          </li>
        ))}
      </ul>
      {adding ? (
        <form onSubmit={add} className="flex flex-col gap-3 rounded-3xl bg-card p-4">
          <Select
            label={t("earnings.kind")}
            value={kind}
            onChange={(e) => setKind(e.target.value as Kind)}
            options={[
              { value: "mobile_money", label: t("earnings.kind_mobile_money") },
              { value: "bank", label: t("earnings.kind_bank") },
            ]}
          />
          {kind === "mobile_money" ? (
            <>
              <Select
                label={t("earnings.network")}
                value={network}
                onChange={(e) => setNetwork(e.target.value as Network)}
                options={NETWORKS.map((n) => ({ value: n, label: t(`networks.${n}`) }))}
              />
              <Input
                label={t("earnings.msisdn")}
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                required
                value={msisdn}
                onChange={(e) => setMsisdn(e.target.value)}
              />
            </>
          ) : (
            <>
              <Input
                label={t("earnings.bankName")}
                required
                maxLength={100}
                value={bankName}
                onChange={(e) => setBankName(e.target.value)}
              />
              <Input
                label={t("earnings.accountNumber")}
                required
                inputMode="numeric"
                maxLength={34}
                value={accountNumber}
                onChange={(e) => setAccountNumber(e.target.value)}
              />
            </>
          )}
          <Input
            label={t("earnings.accountName")}
            hint={t("earnings.accountNameHint")}
            required
            maxLength={100}
            value={accountName}
            onChange={(e) => setAccountName(e.target.value)}
          />
          <div className="flex gap-2">
            <Button type="submit" loading={busy === "add"}>
              {t("earnings.save")}
            </Button>
            {methods.length > 0 && (
              <Button variant="secondary" onClick={() => setAdding(false)}>
                {t("common.back")}
              </Button>
            )}
          </div>
        </form>
      ) : (
        <Button variant="secondary" onClick={() => setAdding(true)}>
          {t("earnings.addMethod")}
        </Button>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </section>
  );
}
