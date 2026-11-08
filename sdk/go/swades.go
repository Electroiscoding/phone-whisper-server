// Package swades provides the official Go client SDK for Swades / Phone Whisper Server.
package swades

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"strings"
	"time"
)

// Client represents a Swades API client.
type Client struct {
	Endpoint   string
	APIKey     string
	ProjectID  string
	HTTPClient *http.Client
}

// ClientOptions configures a new Swades client.
type ClientOptions struct {
	Endpoint   string
	APIKey     string
	ProjectID  string
	HTTPClient *http.Client
}

// NewClient creates an initialized Client.
func NewClient(opts ClientOptions) *Client {
	endpoint := strings.TrimRight(opts.Endpoint, "/")
	if endpoint == "" {
		endpoint = "https://phone-whisper-server.pages.dev"
	}
	httpClient := opts.HTTPClient
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 60 * time.Second}
	}
	projectID := opts.ProjectID
	if projectID == "" {
		projectID = "default"
	}
	return &Client{
		Endpoint:   endpoint,
		APIKey:     opts.APIKey,
		ProjectID:  projectID,
		HTTPClient: httpClient,
	}
}

// ChatMessage represents a single message in a chat completion request.
type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// ChatRequest represents the payload sent to /v1/chat/completions.
type ChatRequest struct {
	Model       string        `json:"model"`
	Messages    []ChatMessage `json:"messages"`
	Temperature float64       `json:"temperature,omitempty"`
	Stream      bool          `json:"stream,omitempty"`
}

// ChatChoice represents an individual choice returned by chat completions.
type ChatChoice struct {
	Index   int         `json:"index"`
	Message ChatMessage `json:"message"`
}

// ChatResponse represents the response from /v1/chat/completions.
type ChatResponse struct {
	ID      string       `json:"id"`
	Choices []ChatChoice `json:"choices"`
}

// ChatCompletion calls the /v1/chat/completions endpoint.
func (c *Client) ChatCompletion(ctx context.Context, req ChatRequest) (*ChatResponse, error) {
	if req.Model == "" {
		req.Model = "qwen2.5-0.5b-instruct"
	}
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to encode request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", c.Endpoint+"/v1/chat/completions", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	if c.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+c.APIKey)
	}

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBytes, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("chat completion failed (status %d): %s", resp.StatusCode, string(respBytes))
	}

	var chatResp ChatResponse
	if err := json.NewDecoder(resp.Body).Decode(&chatResp); err != nil {
		return nil, fmt.Errorf("failed to parse response: %w", err)
	}
	return &chatResp, nil
}

// TranscribeResponse holds the transcribed text.
type TranscribeResponse struct {
	Text string `json:"text"`
}

// TranscribeAudio calls the /v1/audio/transcriptions endpoint with raw audio bytes.
func (c *Client) TranscribeAudio(ctx context.Context, audioBytes []byte, filename string) (string, error) {
	var b bytes.Buffer
	w := multipart.NewWriter(&b)

	part, err := w.CreateFormFile("file", filename)
	if err != nil {
		return "", err
	}
	if _, err := part.Write(audioBytes); err != nil {
		return "", err
	}
	if err := w.Close(); err != nil {
		return "", err
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", c.Endpoint+"/v1/audio/transcriptions", &b)
	if err != nil {
		return "", err
	}
	httpReq.Header.Set("Content-Type", w.FormDataContentType())
	if c.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+c.APIKey)
	}

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBytes, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("transcription failed (status %d): %s", resp.StatusCode, string(respBytes))
	}

	var tr TranscribeResponse
	if err := json.NewDecoder(resp.Body).Decode(&tr); err != nil {
		return "", err
	}
	return tr.Text, nil
}

// SynthesizeSpeech calls /v1/audio/speech to synthesize audio WAV binary.
func (c *Client) SynthesizeSpeech(ctx context.Context, text, voice string) ([]byte, error) {
	if voice == "" {
		voice = "amy"
	}
	payload, _ := json.Marshal(map[string]string{
		"model": "piper",
		"input": text,
		"voice": voice,
	})

	httpReq, err := http.NewRequestWithContext(ctx, "POST", c.Endpoint+"/v1/audio/speech", bytes.NewReader(payload))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	if c.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+c.APIKey)
	}

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBytes, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("speech synthesis failed (status %d): %s", resp.StatusCode, string(respBytes))
	}

	return io.ReadAll(resp.Body)
}

// Telemetry returns system health and hardware telemetry metrics.
func (c *Client) Telemetry(ctx context.Context) (map[string]interface{}, error) {
	httpReq, err := http.NewRequestWithContext(ctx, "GET", c.Endpoint+"/telemetry", nil)
	if err != nil {
		return nil, err
	}

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}
	return result, nil
}

// Health checks the /v1/health endpoint.
func (c *Client) Health(ctx context.Context) (map[string]interface{}, error) {
	httpReq, err := http.NewRequestWithContext(ctx, "GET", c.Endpoint+"/v1/health", nil)
	if err != nil {
		return nil, err
	}

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}
	return result, nil
}
