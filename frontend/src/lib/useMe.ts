import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

/** The signed-in user's roles, for hiding actions they cannot take. The API still enforces them. */
export function useMe() {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity, retry: false });
  const roles = me.data?.roles ?? [];
  return {
    me: me.data,
    can: (...allowed: string[]) => roles.includes("admin") || allowed.some((r) => roles.includes(r)),
  };
}
