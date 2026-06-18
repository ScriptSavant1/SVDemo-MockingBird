import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "@/store/auth";

const MOCK_TOKEN = "eyJhbGciOiJIUzI1NiJ9.test.sig";
const MOCK_USER = { username: "testuser", role: "SV_TEAM" };

beforeEach(() => {
  useAuthStore.getState().logout();
});

describe("auth store", () => {
  it("starts unauthenticated with null token and user", () => {
    const { token, user, isAuthenticated } = useAuthStore.getState();
    expect(isAuthenticated).toBe(false);
    expect(token).toBeNull();
    expect(user).toBeNull();
  });

  it("login() sets token, user, and isAuthenticated=true", () => {
    useAuthStore.getState().login(MOCK_TOKEN, MOCK_USER);
    const { token, user, isAuthenticated } = useAuthStore.getState();
    expect(isAuthenticated).toBe(true);
    expect(token).toBe(MOCK_TOKEN);
    expect(user?.username).toBe("testuser");
    expect(user?.role).toBe("SV_TEAM");
  });

  it("logout() clears token, user, and isAuthenticated", () => {
    useAuthStore.getState().login(MOCK_TOKEN, MOCK_USER);
    useAuthStore.getState().logout();
    const { token, user, isAuthenticated } = useAuthStore.getState();
    expect(isAuthenticated).toBe(false);
    expect(token).toBeNull();
    expect(user).toBeNull();
  });

  it("getState().token returns current token for API client injection", () => {
    useAuthStore.getState().login(MOCK_TOKEN, MOCK_USER);
    expect(useAuthStore.getState().token).toBe(MOCK_TOKEN);
  });
});
