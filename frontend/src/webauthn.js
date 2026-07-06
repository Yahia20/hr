// WebAuthn (device fingerprint) helpers: the server speaks base64url JSON,
// the browser API speaks ArrayBuffers — these translate between the two.
import { api } from "./api";

const b64uToBuf = (s) =>
  Uint8Array.from(
    atob(s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4)) % 4)),
    (c) => c.charCodeAt(0)
  );

const bufToB64u = (buf) =>
  btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");

export const webauthnSupported = () =>
  typeof window !== "undefined" && !!window.PublicKeyCredential && !!navigator.credentials;

/** Register this device's fingerprint/biometric as a credential. */
export async function registerFingerprint(deviceLabel = "") {
  const opts = await api.waRegisterBegin();
  opts.challenge = b64uToBuf(opts.challenge);
  opts.user.id = b64uToBuf(opts.user.id);
  (opts.excludeCredentials || []).forEach((c) => (c.id = b64uToBuf(c.id)));
  const cred = await navigator.credentials.create({ publicKey: opts });
  const payload = {
    id: cred.id,
    rawId: bufToB64u(cred.rawId),
    type: cred.type,
    authenticatorAttachment: cred.authenticatorAttachment || undefined,
    clientExtensionResults: cred.getClientExtensionResults(),
    response: {
      clientDataJSON: bufToB64u(cred.response.clientDataJSON),
      attestationObject: bufToB64u(cred.response.attestationObject),
      transports: cred.response.getTransports ? cred.response.getTransports() : [],
    },
  };
  return api.waRegisterComplete({ credential: payload, device_label: deviceLabel });
}

/** Ask the device for a fingerprint assertion to attach to a clock action. */
export async function getClockAssertion() {
  const opts = await api.waClockBegin();
  opts.challenge = b64uToBuf(opts.challenge);
  (opts.allowCredentials || []).forEach((c) => (c.id = b64uToBuf(c.id)));
  const cred = await navigator.credentials.get({ publicKey: opts });
  return {
    id: cred.id,
    rawId: bufToB64u(cred.rawId),
    type: cred.type,
    authenticatorAttachment: cred.authenticatorAttachment || undefined,
    clientExtensionResults: cred.getClientExtensionResults(),
    response: {
      clientDataJSON: bufToB64u(cred.response.clientDataJSON),
      authenticatorData: bufToB64u(cred.response.authenticatorData),
      signature: bufToB64u(cred.response.signature),
      userHandle: cred.response.userHandle ? bufToB64u(cred.response.userHandle) : undefined,
    },
  };
}

/** Current GPS position as a small plain object; rejects on denial/timeout. */
export function getPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("geo_unsupported"));
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: Math.round(pos.coords.accuracy || 0),
        }),
      (err) => reject(Object.assign(new Error("geo_denied"), { code: err.code })),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }
    );
  });
}
