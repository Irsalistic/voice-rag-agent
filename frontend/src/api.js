export async function getJSON(path) {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(await readError(response))
  }
  return response.json()
}

export async function postJSON(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    throw new Error(await readError(response))
  }
  return response.json()
}

export async function readError(response) {
  try {
    const payload = await response.json()
    if (typeof payload.detail === "string") return payload.detail
    if (Array.isArray(payload.detail)) {
      return payload.detail.map((item) => item.msg).join(" ")
    }
  } catch {
    // The body was not JSON.
  }
  return `Request failed (${response.status})`
}
