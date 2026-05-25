// ui/features/auth/provider.tsx

'use client';

import { createContext, ReactNode, useContext } from "react";
import {
  useQuery,
  useMutation,
  UseMutationResult,
  QueryClient,
} from "@tanstack/react-query";
import { useToast } from "@/features/toast";

// Define User type based on API structure
export type User = {
  id: number;
  username: string;
  email: string;
  role: 'admin' | 'manager' | 'member';
};

// Define the shape of login data
type LoginData = {
  username: string;
  password: string;
};

// Define the shape of registration data
type RegisterData = {
  username: string;
  email: string;
  password: string;
};

// Type definition for the Authentication Context
type AuthContextType = {
  user: User | null;
  isLoading: boolean;
  error: Error | null;
  loginMutation: UseMutationResult<User, Error, LoginData>;
  logoutMutation: UseMutationResult<void, Error, void>;
  registerMutation: UseMutationResult<User, Error, RegisterData>;
};

// Next.js BFF route paths (local proxy, not backend API)
const BFF_ROUTES = {
  USER: "/api/user",
  LOGIN: "/api/login",
  REGISTER: "/api/register",
  LOGOUT: "/api/logout",
} as const;

// Create context with null as default value
export const AuthContext = createContext<AuthContextType | null>(null);

// API Helper function to make requests
const apiRequest = async (
  method: string,
  endpoint: string,
  data?: any
): Promise<Response> => {
  const options: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include", // Important for cookies/sessions
  };

  if (data) {
    options.body = JSON.stringify(data);
  }

  const response = await fetch(endpoint, options);
  
  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.message || "Something went wrong");
  }
  
  return response;
};

// Custom error handling for query functions
type QueryFnOptions = {
  on401?: "returnNull" | "throwError";
};

// Create a query function that handles common error cases
const getQueryFn = <T = unknown>(options: QueryFnOptions = {}) =>
  async ({ queryKey }: { queryKey: string[] }): Promise<T | null> => {
    const [endpoint] = queryKey;
    try {
      const response = await fetch(endpoint, {
        method: "GET",
        credentials: "include",
      });

      if (response.status === 401) {
        if (options.on401 === "returnNull") {
          return null;
        }
        throw new Error("Not authenticated");
      }

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.message || "Something went wrong");
      }

      return await response.json() as T;
    } catch (error) {
      throw error;
    }
  };

// Create a singleton QueryClient to be used in the AuthProvider
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

// Create the Authentication Provider component
export function AuthProvider({ children }: { children: ReactNode }) {
  const { toast } = useToast();
  
  // Query to fetch the current user
  const {
    data: user,
    error,
    isLoading,
  } = useQuery({
    queryKey: [BFF_ROUTES.USER],
    queryFn: async (): Promise<User | null> => {
      try {
        const response = await fetch(BFF_ROUTES.USER, {
          method: "GET",
          credentials: "include",
        });
        if (response.status === 401) {
          return null;
        }
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.message || "Something went wrong");
        }
        return await response.json() as User;
      } catch (error) {
        throw error;
      }
    },
    enabled: false, // Disabled - using UserContext temporarily
  });

  // Mutation to handle login
  const loginMutation = useMutation({
    mutationFn: async (credentials: LoginData) => {
      const res = await apiRequest("POST", BFF_ROUTES.LOGIN, credentials);
      return await res.json();
    },
    onSuccess: (userData: User) => {
      queryClient.setQueryData([BFF_ROUTES.USER], userData);
      toast({
        title: "Login successful",
        description: `Welcome back, ${userData.username}!`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Login failed",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // Mutation to handle registration
  const registerMutation = useMutation({
    mutationFn: async (credentials: RegisterData) => {
      const res = await apiRequest("POST", BFF_ROUTES.REGISTER, credentials);
      return await res.json();
    },
    onSuccess: (userData: User) => {
      queryClient.setQueryData([BFF_ROUTES.USER], userData);
      toast({
        title: "Registration successful",
        description: `Welcome, ${userData.username}!`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Registration failed",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // Mutation to handle logout
  const logoutMutation = useMutation({
    mutationFn: async () => {
      await apiRequest("POST", BFF_ROUTES.LOGOUT);
    },
    onSuccess: () => {
      queryClient.setQueryData([BFF_ROUTES.USER], null);
      toast({
        title: "Logged out",
        description: "You have been logged out successfully",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Logout failed",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // Provide the authentication context to all children
  return (
    <AuthContext.Provider
      value={{
        user: (user ?? null) as User | null,
        isLoading,
        error,
        loginMutation,
        logoutMutation,
        registerMutation,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// Custom hook to use the authentication context
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}