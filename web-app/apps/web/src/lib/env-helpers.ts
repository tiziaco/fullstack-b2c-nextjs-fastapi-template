const nodeEnv = process.env.NODE_ENV || "development"

export const isDevelopment = nodeEnv === "development"
export const isProduction = nodeEnv === "production"
export const isTest = nodeEnv === "test"
