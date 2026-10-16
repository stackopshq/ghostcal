// The "send meeting link" form either posts a pasted link or asks the server to create a
// kMeet room. The two shapes must not mix: the API refuses a body with both or neither.

import { afterEach, describe, expect, it, vi } from "vitest";

const authedFetch = vi.fn<(...args: unknown[]) => Promise<unknown>>(
  async () => ({}),
);

vi.mock("@/lib/auth", () => ({
  authedFetch: (...args: unknown[]) => authedFetch(...args),
}));

import {
  KMEET_ROOM_PREFIX,
  generateMeetingRoom,
  shareMeetingLink,
} from "@/lib/meetings";

afterEach(() => authedFetch.mockClear());

function bodyOf(call: unknown[]): unknown {
  return JSON.parse((call[1] as { body: string }).body);
}

describe("meeting link requests", () => {
  it("posts a pasted link as url only", async () => {
    await shareMeetingLink("b1", "https://zoom.us/j/1");
    expect(authedFetch.mock.calls[0][0]).toBe(
      "/v1/me/meetings/b1/meeting-link",
    );
    expect(bodyOf(authedFetch.mock.calls[0])).toEqual({
      url: "https://zoom.us/j/1",
    });
  });

  it("asks for a kMeet room with the provider only", async () => {
    await generateMeetingRoom("b1", "kmeet");
    expect(authedFetch.mock.calls[0][0]).toBe(
      "/v1/me/meetings/b1/meeting-link",
    );
    expect(bodyOf(authedFetch.mock.calls[0])).toEqual({ provider: "kmeet" });
  });

  it("recognises the rooms the server generates", () => {
    expect(KMEET_ROOM_PREFIX).toBe("https://kmeet.infomaniak.com/");
  });
});
