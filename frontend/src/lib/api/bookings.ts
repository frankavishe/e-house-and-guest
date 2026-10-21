// Server-side reads for the signed-in booking pages (US2). Each returns null when the
// booking is unknown or not the viewer's (the API answers 404 for both).
import type { Schemas } from "./client";
import { serverApi } from "./server";

export type Booking = Schemas["BookingOut"];
export type BookingSummary = Schemas["BookingSummary"];
export type BookingStatus = Booking["status"];
export type Receipt = Schemas["Receipt"];
export type BookingPage = Schemas["Page_BookingSummary_"];

export async function getBooking(id: string): Promise<Booking | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/bookings/{booking_id}", {
    params: { path: { booking_id: id } },
  });
  return data ?? null;
}

/** The receipt, or `notPaid` when the booking has no successful payment yet. */
export async function getReceipt(
  id: string,
): Promise<{ receipt: Receipt | null; notPaid: boolean }> {
  const api = await serverApi();
  const { data, response } = await api.GET("/api/v1/bookings/{booking_id}/receipt", {
    params: { path: { booking_id: id } },
  });
  return { receipt: data ?? null, notPaid: response.status === 409 };
}

export async function listBookings(
  role: "renter" | "owner",
  page: number,
  pageSize: number,
  status?: BookingStatus,
): Promise<BookingPage | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/bookings", {
    params: { query: { role, page, page_size: pageSize, status } },
  });
  return data ?? null;
}
