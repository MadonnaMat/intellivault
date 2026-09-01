"use client";

import { Button, Result } from "antd";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <main>
      <Result
        status="warning"
        title="Something went wrong"
        subTitle="We couldn't reach the server. Your session is still fine — try again."
        extra={
          <Button type="primary" onClick={reset} data-testid="error-retry">
            Retry
          </Button>
        }
      />
    </main>
  );
}
