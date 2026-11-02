// Server-side reads for messaging and public profiles (US6). Each returns null when the
// conversation or user is unknown or not visible to the viewer (the API answers 404).
import type { Schemas } from "./client";
import { serverApi } from "./server";

export type Conversation = Schemas["ConversationOut"];
export type Message = Schemas["MessageOut"];
export type Inbox = Schemas["Inbox"];
export type Review = Schemas["ReviewOut"];
export type UserReviews = Schemas["UserReviews"];

export async function getInbox(page: number, pageSize: number): Promise<Inbox | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/conversations", {
    params: { query: { page, page_size: pageSize } },
  });
  return data ?? null;
}

/** The conversation and its latest messages (reading them marks them read). */
export async function getThread(
  id: string,
): Promise<{ conversation: Conversation; messages: Message[] } | null> {
  const api = await serverApi();
  const path = { conversation_id: id };
  const [conv, msgs] = await Promise.all([
    api.GET("/api/v1/conversations/{conversation_id}", { params: { path } }),
    api.GET("/api/v1/conversations/{conversation_id}/messages", { params: { path } }),
  ]);
  if (!conv.data || !msgs.data) return null;
  return { conversation: conv.data, messages: msgs.data.items };
}

export async function getUserReviews(id: string, page: number): Promise<UserReviews | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/users/{user_id}/reviews", {
    params: { path: { user_id: id }, query: { page, page_size: 10 } },
  });
  return data ?? null;
}
