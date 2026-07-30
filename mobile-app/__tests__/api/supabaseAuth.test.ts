import { sendPhoneOtp, verifyPhoneOtp } from "../../src/api/supabaseAuth";
import { ApiError } from "../../src/api/errors";
import { SUPABASE_ANON_KEY, SUPABASE_URL } from "../../src/config";

function mockFetchOnce(body: unknown, ok = true, status = 200) {
  (global.fetch as jest.Mock).mockResolvedValueOnce({
    ok,
    status,
    json: async () => body,
  });
}

describe("sendPhoneOtp", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("posts to /auth/v1/otp with the apikey header and phone body", async () => {
    mockFetchOnce({});

    await sendPhoneOtp("+4791234567");

    const [url, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe(`${SUPABASE_URL}/auth/v1/otp`);
    expect(options.headers.apikey).toBe(SUPABASE_ANON_KEY);
    expect(JSON.parse(options.body)).toEqual({ phone: "+4791234567" });
  });

  it("throws ApiError('backend', ...) with Supabase's own error message on failure", async () => {
    mockFetchOnce({ msg: "Invalid phone number" }, false, 400);

    await expect(sendPhoneOtp("bad")).rejects.toMatchObject({ kind: "backend", message: "Invalid phone number" });
  });

  it("throws ApiError('network', ...) when fetch rejects", async () => {
    (global.fetch as jest.Mock).mockRejectedValueOnce(new Error("no route to host"));

    await expect(sendPhoneOtp("+4791234567")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("verifyPhoneOtp", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("posts to /auth/v1/verify with type=sms and returns the session", async () => {
    mockFetchOnce({ access_token: "abc", refresh_token: "def", expires_in: 3600, token_type: "bearer" });

    const session = await verifyPhoneOtp("+4791234567", "123456");

    const [url, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe(`${SUPABASE_URL}/auth/v1/verify`);
    expect(JSON.parse(options.body)).toEqual({ type: "sms", phone: "+4791234567", token: "123456" });
    expect(session.access_token).toBe("abc");
  });

  it("throws ApiError('backend', ...) with a status code when the code is wrong", async () => {
    mockFetchOnce({ error_description: "Token has expired or is invalid" }, false, 403);

    await expect(verifyPhoneOtp("+4791234567", "000000")).rejects.toMatchObject({
      kind: "backend",
      message: "Token has expired or is invalid",
      statusCode: 403,
    });
  });
});
