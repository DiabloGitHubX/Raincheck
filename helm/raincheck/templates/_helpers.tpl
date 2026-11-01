{{/*
Return the chart name.
*/}}
{{- define "raincheck.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Return the full application name.
*/}}
{{- define "raincheck.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s" (include "raincheck.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}