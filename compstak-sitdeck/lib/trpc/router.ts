import { router, publicProcedure } from "./server";
import { mapRouter } from "./routers/map";

export const appRouter = router({
  health: publicProcedure.query(() => ({
    status: "ok",
    timestamp: new Date().toISOString(),
  })),
  map: mapRouter,
});

export type AppRouter = typeof appRouter;
