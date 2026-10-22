// Server-side fetchers for the US7 admin screens (categories, users, abuse reports, bookings,
// stats). Each returns null when the API refuses or is unreachable.
import type { Schemas } from "./client";
import { serverApi } from "./server";

export type AdminCategory = Schemas["AdminCategoryOut"];
export type AdminUser = Schemas["AdminUserOut"];
export type AdminReport = Schemas["AdminReportOut"];
export type AdminBooking = Schemas["AdminBookingSummary"];
export type Stats = Schemas["StatsOut"];
export type StatsGroup = Stats["group_by"];
export type ReportStatus = AdminReport["status"];

export async function getAdminCategories(): Promise<AdminCategory[] | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/admin/categories");
  return data ?? null;
}

export async function getAdminUsers(
  q: string | undefined,
  status: "active" | "suspended" | undefined,
  page: number,
): Promise<Schemas["Page_AdminUserOut_"] | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/admin/users", {
    params: { query: { q: q || undefined, status, page } },
  });
  return data ?? null;
}

export async function getAbuseReports(
  status: ReportStatus,
  page: number,
): Promise<Schemas["Page_AdminReportOut_"] | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/admin/reports-abuse", {
    params: { query: { status, page } },
  });
  return data ?? null;
}

export async function getAdminBookings(query: {
  status?: AdminBooking["status"];
  q?: string;
  attention?: boolean;
  page: number;
}): Promise<Schemas["Page_AdminBookingSummary_"] | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/admin/bookings", {
    params: { query: { ...query, q: query.q || undefined } },
  });
  return data ?? null;
}

export async function getStats(
  from: string | undefined,
  to: string | undefined,
  groupBy: StatsGroup,
): Promise<Stats | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/admin/stats", {
    params: { query: { from, to, group_by: groupBy } },
  });
  return (data as Stats | undefined) ?? null;
}
