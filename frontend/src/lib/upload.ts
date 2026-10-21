// Direct-to-storage uploads (R12): the API hands out a presigned PUT, the browser sends the
// file straight to object storage, and the API is told afterwards.

export type PresignedPut = {
  upload_url: string;
  storage_key: string;
  headers: { [key: string]: string };
};

/** PUT `file` to a presigned URL from `presign`; the storage key, or null on failure. */
export async function uploadFile(
  presign: () => Promise<PresignedPut | undefined>,
  file: File,
): Promise<string | null> {
  const target = await presign();
  if (!target) return null;
  const res = await fetch(target.upload_url, {
    method: "PUT",
    headers: target.headers,
    body: file,
  });
  return res.ok ? target.storage_key : null;
}
