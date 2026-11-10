# Install into a project-local library, leaving system libraries unchanged.
args <- commandArgs(trailingOnly=TRUE)
work <- if(length(args)) args[1] else 'work'
lib <- file.path(work,'r-lib')
dir.create(lib,recursive=TRUE,showWarnings=FALSE)
install.packages(c('fixest','data.table','jsonlite'),repos='https://cloud.r-project.org',lib=lib)
